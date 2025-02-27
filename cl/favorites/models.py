from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator
from django.db import models

from cl.audio.models import Audio
from cl.search.models import OpinionCluster, Docket, RECAPDocument


class Favorite(models.Model):
    user = models.ForeignKey(
        User,
        help_text="The user that owns the favorite",
        related_name="favorites",
        on_delete=models.CASCADE,
    )
    cluster_id = models.ForeignKey(
        OpinionCluster,
        verbose_name='the opinion cluster that is favorited',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    audio_id = models.ForeignKey(
        Audio,
        verbose_name='the audio file that is favorited',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    docket_id = models.ForeignKey(
        Docket,
        verbose_name="the docket that is favorited",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    recap_doc_id = models.ForeignKey(
        RECAPDocument,
        verbose_name="the RECAP document that is favorited",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    date_created = models.DateTimeField(
        help_text="The original creation date for the item",
        auto_now_add=True,
        db_index=True
    )
    date_modified = models.DateTimeField(
        auto_now=True,
        db_index=True,
        null=True,
    )
    name = models.CharField(
        'a name for the alert',
        max_length=100,
    )
    notes = models.TextField(
        'notes about the favorite',
        validators=[MaxLengthValidator(500)],
        max_length=500,
        blank=True
    )

    class Meta:
        unique_together = (
            ('cluster_id', 'user'),
            ('audio_id', 'user'),
            ('docket_id', 'user'),
            ('recap_doc_id', 'user'),
        )

    def __unicode__(self):
        return u'Favorite %s' % self.id
