import tempfile
import shutil

from rest_framework.test import APITestCase

from django.test import override_settings

from location.models import Address, Country, StateProvince

from ..models import Workplace, Picture


def get_test_image_file():
    from django.core.files.images import ImageFile
    file = tempfile.NamedTemporaryFile(suffix='.png')
    return ImageFile(file)


MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class PictureTests(APITestCase):

    @classmethod
    def setUpClass(cls):
        super(PictureTests, cls).setUpClass()
        cls.random_country = Country.objects.create(
            name="Random Country",
            iso_code="RC",
        )
        cls.random_state_province = StateProvince.objects.create(
            name="Random State",
            iso_code="RS",
            country=cls.random_country,
        )
        cls.address = Address.objects.create(
            address_line1='random address 1',
            postal_code='RAN DOM',
            city='random city',
            state_province=cls.random_state_province,
            country=cls.random_country,
        )
        cls.workplace = Workplace.objects.create(
            name="random_workplace",
            details="This is a description of the workplace.",
            seats=40,
            location=cls.address,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def test_create(self):
        """
        Ensure that we can create a picture.
        """
        picture = Picture.objects.create(
            name="random_picture",
            picture=get_test_image_file().name,
            workplace=self.workplace,
        )

        self.assertEqual(picture.__str__(), "random_picture")

    def test_picture_tag_property(self):
        """
        Ensure that we get proper html code with picture_tag.
        """
        picture = Picture.objects.create(
            name="random_picture",
            picture=get_test_image_file().name,
            workplace=self.workplace,
        )

        self.assertEqual(
            picture.picture_tag(),
            '<img href="' + picture.picture.url +
            '" src="' + picture.picture.url +
            '" height="150" />'
        )
