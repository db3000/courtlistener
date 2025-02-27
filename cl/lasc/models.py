# coding=utf-8

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey, \
    GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from cl.lib.models import AbstractJSON, AbstractPDF
from cl.lib.model_helpers import make_pdf_path

from cl.lib.storage import AWSMediaStorage

class UPLOAD_TYPE:
    DOCKET = 1
    NAMES = (
        (DOCKET, 'JSON Docket'),
    )


class LASCJSON(AbstractJSON):
    """Store the original JSON content from LASC's API.

    Keep the original data in case we ever need to reparse it.
    """
    upload_type = models.SmallIntegerField(
        help_text="The type of JSON file that is uploaded",
        choices=UPLOAD_TYPE.NAMES,
    )
    sha1 = models.CharField(
        help_text="SHA1 hash of case data. Generated by hashing a copy of the "
                  "JSON with whitespace removed.",
        max_length=128,
    )

    class Meta:
        verbose_name = 'LASC JSON File'


class LASCPDF(AbstractPDF):
    """Use the content framework to associate PDFs with our dockets
    """
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    """
    Do we want to have a different file path generator <----
    """

    filepath_s3 = models.FileField(
        help_text="The path of the file in the s3 bucket.",
        upload_to=make_pdf_path,
        storage=AWSMediaStorage(),
        max_length=150,
        blank=True,
    )
    docket_number = models.CharField(
        help_text="Docket number for the case. E.g. 19LBCV00507, "
                  "19STCV28994, or even 30-2017-00900866-CU-AS-CJC.",
        max_length=300,
        db_index=True,
    )
    document_id = models.CharField(
        help_text="Internal Document Id",
        max_length=40,
        db_index=True,
    )

    class Meta:
        verbose_name = 'LASC PDF'


class QueuedCase(models.Model):
    """Cases we have yet to fetch

    This table is populated by crawling the date search interface.
    """

    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified",
        auto_now=True,
        db_index=True,
    )
    internal_case_id = models.CharField(
        help_text="Internal case ID. Typically a combination of the docket "
                  "number, district, and division code.",
        max_length=300,
        db_index=True,
        blank=True,
    )
    # These fields are only available in the date search results, so we save
    # them here, and eventually populate them in the Docket table.
    judge_code = models.CharField(
        help_text="Internal judge code assigned to the case. First letter of "
                  "judge's last name, and then four digits.",
        max_length=10,
        blank=True,
    )
    case_type_code = models.CharField(
        help_text="A code representing the type of case (similar to the "
                  "federal nature of suit code in PACER). E.g. '1601' "
                  "represents 'Fraud (no contract) (General Jurisdiction)'.",
        max_length=10,
        blank=True,
    )

    @property
    def case_url(self):
        return '/'.join(["https://media.lacourt.org/api/AzureApi",
                        self.internal_case_id])

    def __unicode__(self):
        return "%s" % self.internal_case_id

    class Meta:
        verbose_name = "Queued Case"


class CaseIDQuerySet(models.query.QuerySet):
    """Add filtering by case_id string.

    In our Docket model, we break up the case_id into the docket_number,
    district, and division_code. This is great for granularity, but makes it
    difficult to look them up by case_id, a common need. This class adds the
    ability to do a query like:

        Docket.objects.filter(case_id='19STCV25157;SS;CV')

    """
    def filter(self, *args, **kwargs):
        clone = self._clone()
        case_id = kwargs.pop('case_id', None)
        if case_id:
            case_id_parts = case_id.split(';')
            clone.query.add_q(Q(docket_number=case_id_parts[0],
                                district=case_id_parts[1],
                                division_code=case_id_parts[2]))

        # Add the rest of the args & kwargs
        clone.query.add_q(Q(*args, **kwargs))
        return clone


class Docket(models.Model):
    """High-level table to contain all other LASC-related data"""
    json_document = GenericRelation(
        LASCJSON,
        help_text="JSON files associated with this docket.",
        related_name='dockets',
        null=True,
        blank=True,
    )
    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified",
        auto_now=True,
        db_index=True,
    )
    date_checked = models.DateTimeField(
        help_text="Datetime case was last pulled or checked from LASC",
        null=True,
        blank=True,
        db_index=True,
    )
    date_filed = models.DateField(
        help_text="The date the case was filed",
        null=True,
        blank=True,
    )
    date_disposition = models.DateField(
        help_text="The date the case was disposed by the court",
        null=True,
        blank=True,
    )
    docket_number = models.CharField(
        help_text="Docket number for the case. E.g. 19LBCV00507, "
                  "19STCV28994, or even 30-2017-00900866-CU-AS-CJC.",
        max_length=300,
        db_index=True,
    )
    district = models.CharField(
        help_text="District is a 2-3 character code representing court "
                  "locations; For Example BUR means Burbank",
        max_length=10,
        blank=True,
    )
    division_code = models.CharField(
        help_text="Division. E.g. civil (CV), civil probate (CP), etc.",
        max_length=10,
        blank=True,
    )
    disposition_type = models.TextField(
        help_text="Disposition type",
        blank=True
    )
    disposition_type_code = models.CharField(
        help_text="Disposition type code",
        max_length=10,
        blank=True,
    )
    case_type_str = models.TextField(
        help_text="Case type description",
        blank=True,
    )
    case_type_code = models.CharField(
        help_text="Case type code",
        max_length=10,
        blank=True,
    )
    case_name = models.TextField(
        help_text="The name of the case",
        blank=True,
    )
    judge_code = models.CharField(
        help_text="Internal judge code assigned to the case",
        max_length=10,
        blank=True,
    )
    judge_name = models.TextField(
        help_text="The judge that the case was assigned to",
        blank=True,
    )
    courthouse_name = models.TextField(
        help_text="The courthouse name",
        blank=True,
    )
    date_status = models.DateTimeField(
        help_text="Date status was updated",
        null=True,
        blank=True,
    )
    status_code = models.CharField(
        help_text="Court status code associated with current status",
        max_length=20,
        blank=True,
    )
    status_str = models.TextField(
        help_text="The status of the case",
        blank=True,
    )

    objects = CaseIDQuerySet.as_manager()

    class Meta:
        index_together = ('docket_number', 'district', 'division_code')

    @property
    def case_id(self):
        return ';'.join([self.docket_number, self.district,
                         self.division_code])

    def __unicode__(self):
        return "%s" % self.case_id


class QueuedPDF(models.Model):
    """PDFs we have yet to download."""

    docket = models.ForeignKey(
        Docket,
        related_name='queued_pdfs',
        on_delete=models.CASCADE,
    )

    date_created = models.DateTimeField(
        help_text="The time when this item was created",
        auto_now_add=True,
        db_index=True,
    )
    date_modified = models.DateTimeField(
        help_text="The last moment when the item was modified",
        auto_now=True,
        db_index=True,
    )
    internal_case_id = models.CharField(
        help_text="Internal case ID. Typically a combination of the docket "
                  "number, district, and division code.",
        max_length=300,
        db_index=True,
    )
    document_id = models.CharField(
        help_text="Internal Document Id",
        max_length=40,
        db_index=True,
    )

    @property
    def document_url(self):
        return '/'.join(["https://media.lacourt.org/api/AzureApi/ViewDocument",
                        self.internal_case_id,
                        self.document_id])

    def __unicode__(self):
        return "%s" % self.document_id

    class Meta:
        verbose_name = "Queued PDF"


class DocumentImage(models.Model):
    """Represents documents that are filed and scanned into the online system,
    most of which are available to us.
    """

    """
        # caseNumber
        # pageCount
        # IsPurchaseable
        # createDateString
        # documentType
        # "docFilingDateString": "06/07/2019",
        # "documentURL": "",
        # "createDate": "2019-06-07T00:00:00-07:00",
        # "IsInCart": false,
        # "OdysseyID": "",
        # "IsDownloadable": true,
        # "documentTypeID": "",
        # "docId": "1769824611",
        # "description": "Answer",
        # "volume": "",
        # "appId": "",
        # "IsViewable": true,
        # "securityLevel": 0,
        # "IsEmailable": false,
        # "imageTypeId": 3,
        # "IsPurchased": true,
        # "docFilingDate": "2019-06-07T00:00:00-07:00",
        # "docPart":
    """

    docket = models.ForeignKey(
        Docket,
        related_name='document_images',
        on_delete=models.CASCADE,
    )
    pdf_document = GenericRelation(
        LASCPDF,
        help_text="PDF document.",
        related_name='document_images',
        null=True,
        blank=True,
    )
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
    # Corresponds with create_date in docket JSON
    date_processed = models.DateTimeField(
        help_text="The date the document was created in the lasc system, "
                  "whether by attorney upload, clerk processing, etc.",
        null=True,
        blank=True,
    )
    date_filed = models.DateTimeField(
        help_text="The date the document was filed in the system",
        null=True,
        blank=True,
    )
    doc_id = models.CharField(
        help_text="Internal document ID in LASC system used for uniquely "
                  "identifying the document",
        max_length=30,
    )
    page_count = models.IntegerField(
        help_text="Page count for this document",
        blank=True,
        null=True,
    )
    document_type = models.TextField(
        help_text="Type of document. Typically blank; still exploring "
                  "possible meaning in LASC system.",
        blank=True,
    )
    document_type_code = models.CharField(
        help_text="Type of document as a code. We believe this corresponds to "
                  "the document_type field.",
        max_length=20,
        blank=True,
    )
    image_type_id = models.CharField(
        help_text="Image type ID. Still exploring possible meanings in LASC "
                  "system.",
        max_length=20,
        blank=True,
    )
    app_id = models.TextField(
        help_text="ID for filing application, if any.",
        blank=True,
    )
    odyssey_id = models.TextField(
        help_text="Typically null; likely a vendor-provided code. Still "
                  "exploring possible meanings in LASC system.",
        blank=True,
    )
    is_downloadable = models.BooleanField(
        help_text="Did the user who got the docket have permission to "
                  "download this item?",
    )
    security_level = models.CharField(
        help_text="Document security level",
        max_length=10,
        blank=True,
    )
    description = models.TextField(
        help_text="Document description",
        blank=True,
    )
    volume = models.TextField(
        help_text="Document volume. Still exploring possible meanings in LASC "
                  "system.",
        blank=True,
    )
    doc_part = models.TextField(
        help_text="Document part. Still exploring possible meanings in LASC "
                  "system.",
        blank=True,
    )

    # CourtListener-populated fields, not gathered from the docket JSON or
    # otherwise from LASC.
    is_available = models.BooleanField(
        help_text="Has the document been downloaded",
    )

    @property
    def document_map_url(self):
        """The URL to the document in the Media Access Portal."""
        base_url = 'https://media.lacourt.org/api/AzureApi/'
        path_template = 'ViewDocument/%s/%s'
        return base_url + path_template % (self.docket.case_id, self.doc_id)

    def __unicode__(self):
        return "Scanned PDF  %s for %s" % (self.doc_id,
                                           self.docket.docket_number)
    class Meta:
        verbose_name = "Document Image"
        verbose_name_plural = "Document Images"


class DocumentFiled(models.Model):
    """Filings on the docket whether or not they're digitally available to
    anyone accessing the system.
    """

    """
    # "CaseNumber": "18STCV02953",
    # "Memo": null,
    # "DateFiled": "2019-06-07T00:00:00-07:00",
    # "DateFiledString": "06/07/2019",
    # "Party": "Angel Ortiz Hernandez (Defendant)",
    # "Document": "Answer"]
    """
    docket = models.ForeignKey(
        Docket,
        related_name='documents_filed',
        on_delete=models.CASCADE,
    )
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
    date_filed = models.DateTimeField(
        help_text="Date a document was filed",
    )
    memo = models.TextField(
        help_text="Memo describing document filed",
        blank=True,
    )
    document_type = models.TextField(
        help_text="Document type, whether it's an Answer, a Complaint, etc.",
        blank=True,
    )
    party_str = models.TextField(
        help_text="Filing party for the document",
        blank=True,
    )

    class Meta:
        verbose_name_plural = 'Documents Filed'

    def __unicode__(self):
        return "%s for %s" % (self.document_type, self.docket.docket_number)


class Action(models.Model):
    """Actions registered on a docket"""

    """
        # "IsPurchaseable": false,
        # "Description": "Answer",
        # "PageCount": -1,
        # "AdditionalInformation": "<ul><li>Party: Angel Ortiz Hernandez (Defendant)</li></ul>",
        # "RegisterOfActionDateString": "06/07/2019",
        # "IsPurchased": false,
        # "FilenetID": "",
        # "IsEmailable": false,
        # "IsViewable": false,
        # "OdysseyID": "",
        # "IsInCart": false,
        # "RegisterOfActionDate": "2019-06-07T00:00:00-07:00",
        # "IsDownloadable": false
    """

    docket = models.ForeignKey(
        Docket,
        related_name='actions',
        on_delete=models.CASCADE,
    )
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
    date_of_action = models.DateTimeField(
        help_text="Date of the action entry",
    )
    description = models.TextField(
        help_text="Short description of the document",
        blank=True,
    )
    additional_information = models.TextField(
        help_text="Additional information stored as HTML",
        blank=True,
    )

    class Meta:
        verbose_name = "Action Entry"
        verbose_name_plural = "Action Entries"

    def __unicode__(self):
        return "Action for %s" % self.docket.docket_number


class CrossReference(models.Model):
    """Relations between cases.

    Unfortunately, these cannot be normalized b/c they may refer to cases in
    other jurisdictions, among other issues.
    """

    """
    cross_reference_date_string: "11/08/2001"
    cross_reference_date : 2001-11-07T23:00:00-08:00
    cross_reference_case_number: 37-2011-0095551-
    cross_reference_type_description:  Coordinated Case(s)
    """

    docket = models.ForeignKey(
        Docket,
        related_name='cross_references',
        on_delete=models.CASCADE,
    )
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
    date_cross_reference = models.DateTimeField(
        help_text="Cross reference date",
        null=True,
        blank=True,
    )
    cross_reference_docket_number = models.TextField(
        help_text="Cross reference docket number",
        blank=True,
    )
    cross_reference_type = models.TextField(
        help_text="A description of the type of cross reference",
        blank=True,
    )

    def __unicode__(self):
        return "%s for %s" % (self.cross_reference_type,
                              self.docket.docket_number)

    class Meta:
        verbose_name = "Cross Reference"
        verbose_name_plural = "Cross References"


class Party(models.Model):

    """
    # "EntityNumber": "3",
    # "PartyFlag": "L",
    # "DateOfBirthString": "",
    # "CaseNumber": "18STCV02953",
    # "District": "",
    # "CRSPartyCode": null,
    # "DateOfBirth": "0001-01-01T00:00:00-08:00",
    # "AttorneyFirm": "",
    # "CivasCXCNumber": "",
    # "AttorneyName": "",
    # "PartyDescription": "Defendant",
    # "DivisionCode": "CV",
    # "PartyTypeCode": "D",
    # "Name": "HERNANDEZ ANGEL ORTIZ AKA ANGEL HERNANDEZ"

    """

    docket = models.ForeignKey(
        Docket,
        related_name='parties',
        on_delete=models.CASCADE,
    )
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
    attorney_name = models.TextField(
        help_text="Attorney name",
        blank=True,
    )
    attorney_firm = models.TextField(
        help_text="Attorney firm",
        blank=True,
    )
    entity_number = models.TextField(
        help_text="Order entity/party joined cases system",
        blank=True,
    )
    party_name = models.TextField(
        help_text="Full name of the party",
        blank=True,
    )
    party_flag = models.TextField(
        help_text="Court code representing party",
        blank=True,
    )
    party_type_code = models.TextField(
        help_text="Court code representing party position",
        blank=True,
    )
    party_description = models.TextField(
        help_text="Description of the party",
        blank=True,
    )

    class Meta:
        verbose_name_plural = "Parties"

    def __unicode__(self):
        return "%s for %s" % (self.party_name, self.docket.docket_number)


class TIME_CHOICES:
    PAST = 1
    FUTURE = 2
    NAMES = (
        (PAST, "Proceedings in the past"),
        (FUTURE, "Proceedings in the future"),
    )


class PastProceedingManager(models.Manager):
    def get_queryset(self):
        super_qs = super(PastProceedingManager, self).get_queryset()
        return super_qs.filter(past_or_future=TIME_CHOICES.PAST)


class FutureProceedingManager(models.Manager):
    def get_queryset(self):
        super_qs = super(FutureProceedingManager, self).get_queryset()
        return super_qs.filter(past_or_future=TIME_CHOICES.FUTURE)


class Proceeding(models.Model):

    """
    "ProceedingDateString": "08/24/2018",
    "CourtAlt": "",
    "CaseNumber": "BZ215634",
    "District": "",
    "AMPM": "AM",
    "Memo": "",
    "Address": "",
    "ProceedingRoom": "Department 2F",
    "ProceedingDate": "2018-08-24T00:00:00-07:00",
    "Result": "Held - Order Made",
    "ProceedingTime": " 9:00",
    "Judge": "Lowry, Stephen M.",
    "CourthouseName": "",
    "DivisionCode": "",
    "Event": "DSU - RFO (Modification Hearing)
    """

    docket = models.ForeignKey(
        Docket,
        related_name='proceedings',
        on_delete=models.CASCADE,
    )
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
    past_or_future = models.SmallIntegerField(
        help_text="Is this event in the past or future?",
        choices=TIME_CHOICES.NAMES,
        null=True,
        blank=True,
    )
    # We keep a date a time, and an AM/PM field for this table because each
    # provides useful information and unfortunately the upstream data is
    # provided in this manner. Rather than try to merge them, which may go
    # poorly, we just keep them in the format we've been given them.
    date_proceeding = models.DateTimeField(
        help_text="Date of the past proceeding",
    )
    proceeding_time = models.TextField(
        help_text="Time of the past proceeding in HH:MM string",
        blank=True,
    )
    am_pm = models.TextField(
        help_text="Was the proceeding in the AM or PM",
        blank=True,
    )
    memo = models.TextField(
        help_text="Memo about the proceeding",
        blank=True,
    )
    courthouse_name = models.TextField(
        help_text="Courthouse name for the proceeding",
        blank=True,
    )
    address = models.TextField(
        help_text="Address of the proceeding",
        blank=True,
    )
    proceeding_room = models.TextField(
        help_text="The court room of the proceeding",
        blank=True,
    )
    result = models.TextField(
        help_text="Result of the proceeding",
        blank=True,
    )
    judge_name = models.TextField(
        help_text="Judge in the proceeding",
        blank=True,
    )
    event = models.TextField(
        help_text='Event that occurred. E.g. "Jury Trial"',
        blank=True,
    )

    objects = models.Manager()
    past_objects = PastProceedingManager()
    future_objects = FutureProceedingManager()

    def __unicode__(self):
        return "%s for %s" % (self.event, self.docket.docket_number)


class TentativeRuling(models.Model):
    """
    Sample data taken from random cases.

    "CaseNumber": "VC065473",
    "HearingDate": "2019-07-11T00:00:00-07:00",
    "LocationID": "SE ",
    "Ruling": "SUPER LONG HTML"
    "Department": "SEC",
    "CreationDateString": "07/10/2019",
    "CreationDate": "2019-07-10T14:51:33-07:00",
    "HearingDateString": "07/11/2019"
    """
    docket = models.ForeignKey(
        Docket,
        related_name='tentative_rulings',
        on_delete=models.CASCADE,
    )
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
    date_creation = models.DateTimeField(
        help_text="Still exploring possible meanings in LASC "
                  "system.",
        null=True,
        blank=True,
    )
    date_hearing = models.DateTimeField(
        help_text="The date of the hearing leading to the ruling.",
        null=True,
        blank=True,
    )
    department = models.TextField(
        help_text="Internal court code for department",
        blank=True,
    )
    ruling = models.TextField(
        help_text="The court ruling as HTML",
        blank=True,
    )

    def __unicode__(self):
        return "Tentative ruling for %s" % self.docket.docket_number

    class Meta:
        verbose_name = "Tentative Ruling"
