import openai
import time
import logging
from typing import List, Tuple, Optional
from django.conf import settings
from django.db import transaction
import os

from .analysis_settings import START_DATE, END_DATE, SIMILARITY_THRESHOLD_FOR_FINDING_SIMILAR_ARTICLES
from .models import NewsArticle
import uuid

# Set up logging
logger = logging.getLogger(__name__)

def generate_embeddings(text: str, model: str = "text-embedding-3-small") -> Optional[List[float]]:
    """
    Generate embeddings for given text using OpenAI's embedding API

    Args:
        text (str): The text to generate embeddings for
        model (str): The OpenAI embedding model to use
                    Options: "text-embedding-3-small" (cheaper, fast)
                            "text-embedding-3-large" (more accurate, expensive)

    Returns:
        List[float]: The embedding vector as a list of floats
        None: If embedding generation fails
    """

    # Input validation
    if not text or not text.strip():
        logger.warning("Empty or whitespace-only text provided for embedding")
        return None

    # Clean and truncate text if needed
    text = text.strip()

    # OpenAI embedding models have token limits:
    # text-embedding-3-small: 8191 tokens
    # text-embedding-3-large: 8191 tokens
    # Rough approximation: 1 token ≈ 4 characters for English text
    max_chars = 30000  # Conservative limit to stay under token limit

    if len(text) > max_chars:
        text = text[:max_chars]
        logger.info(f"Text truncated to {max_chars} characters for embedding")

    try:
        # Initialize OpenAI client
        # Make sure you have OPENAI_API_KEY in your environment variables or Django settings
        client = openai.OpenAI(
            api_key=getattr(settings, 'OPENAI_API_KEY', None) or openai.api_key
        )

        # Generate embedding
        response = client.embeddings.create(
            model=model,
            input=text,
            encoding_format="float"  # Returns floats instead of base64
        )

        # Extract the embedding vector
        embedding = response.data[0].embedding

        logger.info(f"Successfully generated embedding of dimension {len(embedding)}")
        return embedding

    except openai.RateLimitError:
        logger.error("OpenAI API rate limit exceeded")
        # You might want to implement retry logic here
        time.sleep(1)  # Simple backoff
        return None

    except openai.APIError as e:
        logger.error(f"OpenAI API error: {e}")
        return None

    except Exception as e:
        logger.error(f"Unexpected error generating embedding: {e}")
        return None


def generate_embeddings_batch(texts: List[str], model: str = "text-embedding-3-small") -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts in a single API call (more efficient)

    Args:
        texts (List[str]): List of texts to generate embeddings for
        model (str): The OpenAI embedding model to use

    Returns:
        List[Optional[List[float]]]: List of embedding vectors, None for failed generations
    """

    OPENAI_API_KEY = os.getenv('OPEN_AI_API_KEY')

    if not texts:
        return []

    # Clean texts and filter out empty ones
    cleaned_texts = []
    original_indices = []

    for i, text in enumerate(texts):
        if text and text.strip():
            cleaned_text = text.strip()
            if len(cleaned_text) > 30000:
                cleaned_text = cleaned_text[:30000]
            cleaned_texts.append(cleaned_text)
            original_indices.append(i)

    if not cleaned_texts:
        return [None] * len(texts)

    try:
        client = openai.OpenAI(
            api_key=OPENAI_API_KEY
        )

        response = client.embeddings.create(
            model=model,
            input=cleaned_texts,
            encoding_format="float"
        )

        # Create result list with None for all positions
        results = [None] * len(texts)

        # Fill in successful embeddings at their original positions
        for i, embedding_data in enumerate(response.data):
            original_index = original_indices[i]
            results[original_index] = embedding_data.embedding

        logger.info(f"Successfully generated {len(cleaned_texts)} embeddings in batch")
        return results

    except Exception as e:
        logger.error(f"Batch embedding generation failed: {e}")
        return [None] * len(texts)


def generate_article_embeddings(article_data: dict) -> dict:
    """
    Helper function to generate all three embeddings for a news article

    Args:
        article_data (dict): Dictionary containing title, summary, etc.

    Returns:
        dict: Dictionary with embedding fields ready for model creation
    """

    title = article_data.get('title', '')
    summary = article_data.get('summary', '')

    # Generate all three embeddings in batch for efficiency
    texts_to_embed = [
        title,
        summary,
        f"{title}\n\n{summary}"  # title + summary combined
    ]

    embeddings = generate_embeddings_batch(texts_to_embed)

    return {
        'title_embedding': embeddings[0],
        'summary_embedding': embeddings[1],
        'title_summary_embedding': embeddings[2]
    }

def assign_story_cluster_id(article: NewsArticle, similarity_threshold: float = SIMILARITY_THRESHOLD_FOR_FINDING_SIMILAR_ARTICLES) -> str:
    """
    Assign a story_cluster_id to an article by finding similar existing articles
    or creating a new cluster if no similar articles are found.

    Args:
        article: The NewsArticle instance to assign a cluster ID to
        similarity_threshold: Minimum similarity score to consider articles as same story

    Returns:
        str: The assigned cluster ID
    """

    if article.story_cluster_id:
        logger.info(f"Article {article.id} already has cluster ID: {article.story_cluster_id}")
        return article.story_cluster_id

    # Try different embedding fields in order of preference
    embedding_fields = ['summary_embedding', 'title_summary_embedding', 'title_embedding']

    for field in embedding_fields:
        embedding = getattr(article, field)
        if not embedding:
            continue

        # Find similar stories using this embedding
        similar_stories = NewsArticle.find_similar_stories(
            embedding_vector=embedding,
            field=field,
            threshold=similarity_threshold,
            exclude_id=article.id
        )

        if similar_stories:
            # Use the cluster ID from the most similar story
            most_similar_article = similar_stories[0][0]  # (article, similarity_score)
            similarity_score = similar_stories[0][1]

            if most_similar_article.story_cluster_id:
                article.story_cluster_id = most_similar_article.story_cluster_id
                article.save()

                logger.info(f"Assigned existing cluster {article.story_cluster_id} to article {article.id} "
                            f"(similarity: {similarity_score:.3f} using {field})")
                return article.story_cluster_id

    # No similar stories found, create new cluster
    new_cluster_id = str(uuid.uuid4())
    article.story_cluster_id = new_cluster_id
    article.save()

    logger.info(f"Created new cluster {new_cluster_id} for article {article.id}")
    return new_cluster_id


def batch_assign_clusters(similarity_threshold: float = 0.8) -> dict:
    """
    Assign cluster IDs to all articles that don't have one yet.
    Processes articles in chronological order (oldest first).

    Args:
        similarity_threshold: Minimum similarity score to group articles

    Returns:
        dict: Statistics about the clustering process
    """

    # Get articles without cluster IDs, ordered by publish date
    articles_without_clusters = NewsArticle.objects.filter(
        story_cluster_id__isnull=True
    ).order_by('publish_date')

    stats = {
        'processed': 0,
        'new_clusters': 0,
        'joined_clusters': 0,
        'skipped_no_embeddings': 0
    }

    logger.info(f"Starting batch clustering for {articles_without_clusters.count()} articles")

    for article in articles_without_clusters:
        # Check if article has any embeddings
        if not any([article.title_embedding, article.summary_embedding, article.title_summary_embedding]):
            stats['skipped_no_embeddings'] += 1
            continue

        original_cluster_count = NewsArticle.objects.filter(
            story_cluster_id__isnull=False
        ).values('story_cluster_id').distinct().count()

        assign_story_cluster_id(article, similarity_threshold)

        new_cluster_count = NewsArticle.objects.filter(
            story_cluster_id__isnull=False
        ).values('story_cluster_id').distinct().count()

        if new_cluster_count > original_cluster_count:
            stats['new_clusters'] += 1
        else:
            stats['joined_clusters'] += 1

        stats['processed'] += 1

        # Log progress every 10 articles
        if stats['processed'] % 10 == 0:
            logger.info(f"Processed {stats['processed']} articles...")

    logger.info(f"Batch clustering complete: {stats}")
    return stats


def analyze_clusters() -> dict:
    """
    Analyze the current state of story clusters.

    Returns:
        dict: Statistics about clusters
    """

    from django.db.models import Count

    # Get cluster statistics
    cluster_stats = NewsArticle.objects.filter(
        story_cluster_id__isnull=False
    ).values('story_cluster_id').annotate(
        article_count=Count('id')
    ).order_by('-article_count')

    total_articles = NewsArticle.objects.count()
    clustered_articles = NewsArticle.objects.filter(story_cluster_id__isnull=False).count()
    unclustered_articles = total_articles - clustered_articles

    # Find largest clusters
    largest_clusters = cluster_stats[:10]

    stats = {
        'total_articles': total_articles,
        'clustered_articles': clustered_articles,
        'unclustered_articles': unclustered_articles,
        'total_clusters': len(cluster_stats),
        'single_article_clusters': sum(1 for c in cluster_stats if c['article_count'] == 1),
        'largest_clusters': [
            {
                'cluster_id': c['story_cluster_id'],
                'article_count': c['article_count'],
                'sample_titles': list(NewsArticle.objects.filter(
                    story_cluster_id=c['story_cluster_id']
                ).values_list('title', flat=True)[:3])
            }
            for c in largest_clusters
        ]
    }

    return stats


def recluster_all_articles(similarity_threshold: float = SIMILARITY_THRESHOLD_FOR_FINDING_SIMILAR_ARTICLES) -> dict:
    """
    Reset all cluster IDs and recluster everything from scratch.
    Use with caution - this will reassign all cluster IDs.

    Args:
        similarity_threshold: Similarity threshold for clustering

    Returns:
        dict: Statistics about the reclustering process
    """

    logger.warning("Starting complete reclustering - all existing cluster IDs will be reset")

    with transaction.atomic():
        # Reset cluster IDs
        # only articles with story_cluster_id == None will be reclustered
        articles = NewsArticle.objects.filter(
            created_at__range=(START_DATE, END_DATE)
        ).update(story_cluster_id=None)

        # Run batch assignment
        stats = batch_assign_clusters(similarity_threshold)

    logger.info(f"Reclustering complete: {stats}")
    return stats