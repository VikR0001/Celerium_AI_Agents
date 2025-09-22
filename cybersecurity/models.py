from django.db import models
from django.utils import timezone

from cybersecurity.analysis_settings import SIMILARITY_THRESHOLD_FOR_FINDING_SIMILAR_ARTICLES


class NewsArticle(models.Model):
    """
    Model to store news articles about data breaches
    """
    title = models.TextField(
        help_text="Title of the data breach incident"
    )

    url = models.TextField(
        unique=True,
        help_text="URL to the source article or report"
    )

    source = models.TextField(
        help_text="Source of the breach information (e.g., news outlet, security firm)"
    )

    summary = models.TextField(
        help_text="Brief summary of the data breach incident"
    )

    publish_date = models.DateTimeField(
        help_text="Date and time when the breach information was published"
    )

    full_text_of_article = models.TextField(
        help_text="Complete text content of the breach report or article"
    )

    number_of_records_breached = models.TextField(
        blank=True,
        null=True,
        help_text="Number of records affected by the breach (stored as string to handle various formats)"
    )

    names_of_threat_actors = models.TextField(
        blank=True,
        null=True,
        help_text="Names of threat actors or groups responsible for the breach"
    )

    # Story clustering and embedding fields
    story_cluster_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Unique identifier for grouping articles about the same underlying breach incident"
    )

    title_embedding = models.JSONField(
        blank=True,
        null=True,
        help_text="Vector embedding of the title text for similarity matching"
    )

    summary_embedding = models.JSONField(
        blank=True,
        null=True,
        help_text="Vector embedding of the summary text for similarity matching"
    )

    title_summary_embedding = models.JSONField(
        blank=True,
        null=True,
        help_text="Vector embedding of combined title and summary for similarity matching"
    )

    # Additional metadata fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when this record was created"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when this record was last updated"
    )

    class Meta:
        db_table = 'news_articles'
        verbose_name = 'News Article'
        verbose_name_plural = 'News Articles'
        ordering = ['-publish_date']
        indexes = [
            models.Index(fields=['publish_date']),
            models.Index(fields=['source']),
            models.Index(fields=['created_at']),
            models.Index(fields=['story_cluster_id']),
        ]

    def __str__(self):
        return f"{self.title} - {self.source}"

    def get_number_of_records_breached_as_int(self):
        """
        Helper method to convert number_of_records_breached to integer
        Returns None if conversion fails
        """
        try:
            return int(self.number_of_records_breached.replace(',', ''))
        except (ValueError, AttributeError):
            return None

    def get_title_summary_text(self):
        """
        Helper method to get combined title and summary text for embedding
        """
        return f"{self.title}\n\n{self.summary}"

    def calculate_similarity_score(self, other_embedding, field='summary_embedding'):
        """
        Calculate cosine similarity with another breach record
        Returns similarity score between 0 and 1
        """
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        embedding1 = getattr(self, field)
        embedding2 = other_embedding

        if not embedding1 or not embedding2:
            return 0.0

        # Convert to numpy arrays and calculate cosine similarity
        vec1 = np.array(embedding1).reshape(1, -1)
        vec2 = np.array(embedding2).reshape(1, -1)

        return cosine_similarity(vec1, vec2)[0][0]

    @classmethod
    def find_similar_stories(cls, embedding_vector, field='summary_embedding', threshold=SIMILARITY_THRESHOLD_FOR_FINDING_SIMILAR_ARTICLES, exclude_id=None):
        """
        Find stories with similar embeddings above the threshold
        """
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        # Get all records with embeddings for the specified field
        queryset = cls.objects.exclude(id=exclude_id) if exclude_id else cls.objects.all()
        # records_with_embeddings = queryset.filter(**{f"{field}__isnull": False})
        records_with_embeddings = queryset.filter(**{f"{field}__isnull": False}).order_by('created_at')

        similar_stories = []
        target_vec = np.array(embedding_vector).reshape(1, -1)

        for record in records_with_embeddings:
            record_embedding = getattr(record, field)
            if record_embedding:
                record_vec = np.array(record_embedding).reshape(1, -1)
                similarity = cosine_similarity(target_vec, record_vec)[0][0]

                if similarity >= threshold:
                    similar_stories.append((record, similarity))

        # Sort by similarity score (highest first)
        return sorted(similar_stories, key=lambda x: x[1], reverse=True)

    def get_cluster_stories(self):
        """
        Get all stories in the same cluster
        """
        if not self.story_cluster_id:
            return NewsArticle.objects.none()

        return NewsArticle.objects.filter(
            story_cluster_id=self.story_cluster_id
        ).exclude(id=self.id)

    def get_threat_actors_list(self):
        """
        Helper method to return threat actors as a list
        Handles cases where multiple actors are separated by commas
        """
        if self.names_of_threat_actors:
            return [actor.strip() for actor in self.names_of_threat_actors.split(',')]
        return []