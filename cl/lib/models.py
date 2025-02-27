from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from cl.lib.storage import IncrementingFileSystemStorage, UUIDFileSystemStorage
from cl.lib.model_helpers import make_json_path, make_pdf_path, \
    make_pdf_thumb_path, make_lasc_json_path


class THUMBNAIL_STATUSES(object):
    NEEDED = 0
    COMPLETE = 1
    FAILED = 2
    NAMES = (
        (NEEDED, "Thumbnail needed"),
        (COMPLETE, "Thumbnail completed successfully"),
        (FAILED, 'Unable to generate thumbnail'),
    )


class AbstractPDF(models.Model):
    """An abstract model to hold PDF-related information"""
    OCR_COMPLETE = 1
    OCR_UNNECESSARY = 2
    OCR_FAILED = 3
    OCR_NEEDED = 4
    OCR_STATUSES = (
        (OCR_COMPLETE, "OCR Complete"),
        (OCR_UNNECESSARY, "OCR Not Necessary"),
        (OCR_FAILED, "OCR Failed"),
        (OCR_NEEDED, "OCR Needed"),
    )
    date_created = models.DateTimeField(
        help_text="The date the file was imported to Local Storage.",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="Timestamp of last update.",
        auto_now=True,
        db_index=True,
    )
    sha1 = models.CharField(
        help_text="The ID used for a document in RECAP",
        max_length=40,  # As in RECAP
        blank=True,
    )
    page_count = models.IntegerField(
        help_text="The number of pages in the document, if known",
        blank=True,
        null=True,
    )
    file_size = models.IntegerField(
        help_text="The size of the file in bytes, if known",
        blank=True,
        null=True,
    )
    filepath_local = models.FileField(
        help_text="The path of the file in the local storage area.",
        upload_to=make_pdf_path,
        storage=IncrementingFileSystemStorage(),
        max_length=1000,
        db_index=True,
        blank=True,
    )
    filepath_ia = models.CharField(
        help_text="The URL of the file in IA",
        max_length=1000,
        blank=True,
    )
    ia_upload_failure_count = models.SmallIntegerField(
        help_text="Number of times the upload to the Internet Archive failed.",
        null=True,
        blank=True,
    )
    thumbnail = models.FileField(
        help_text="A thumbnail of the first page of the document",
        upload_to=make_pdf_thumb_path,
        storage=IncrementingFileSystemStorage(),
        null=True,
        blank=True,
    )
    thumbnail_status = models.SmallIntegerField(
        help_text="The status of the thumbnail generation",
        choices=THUMBNAIL_STATUSES.NAMES,
        default=THUMBNAIL_STATUSES.NEEDED,
    )
    plain_text = models.TextField(
        help_text="Plain text of the document after extraction using "
                  "pdftotext, wpd2txt, etc.",
        blank=True,
    )
    ocr_status = models.SmallIntegerField(
        help_text="The status of OCR processing on this item.",
        choices=OCR_STATUSES,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


class AbstractFile(models.Model):
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified.",
        auto_now=True,
        db_index=True,
    )
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    class Meta:
        abstract = True

    @property
    def file_contents(self):
        with open(self.filepath.path, 'r') as f:
            return f.read().decode('utf-8')

    def print_file_contents(self):
        print(self.file_contents)


class AbstractJSON(AbstractFile):
    filepath = models.FileField(
        help_text="The path of the file in the local storage area.",
        upload_to=make_lasc_json_path,
        max_length=150,
        blank=True,
    )

    class Meta:
        abstract = True

