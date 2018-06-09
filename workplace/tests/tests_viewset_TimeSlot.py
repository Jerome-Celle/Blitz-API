import json
import pytz

from datetime import datetime, timedelta

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model

from blitz_api.factories import UserFactory, AdminFactory

from location.models import Country, StateProvince, Address

from ..models import Period, TimeSlot, Workplace

User = get_user_model()

LOCAL_TIMEZONE = pytz.timezone(settings.TIME_ZONE)


class TimeSlotTests(APITestCase):

    @classmethod
    def setUpClass(cls):
        super(TimeSlotTests, cls).setUpClass()
        cls.client = APIClient()
        cls.user = UserFactory()
        cls.admin = AdminFactory()
        cls.random_country = Country.objects.create(
            name="Random_Country",
            iso_code="RC",
        )
        cls.random_state_province = StateProvince.objects.create(
            name="Random_State",
            iso_code="RS",
            country=cls.random_country,
        )
        cls.address = Address.objects.create(
            address_line1='random_address_1',
            postal_code='RAN_DOM',
            city='random_city',
            state_province=cls.random_state_province,
            country=cls.random_country,
        )
        cls.workplace = Workplace.objects.create(
            name="Blitz",
            seats=40,
            details="short_description",
            location=cls.address,
        )
        cls.period = Period.objects.create(
            name="random_period",
            workplace=cls.workplace,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(weeks=4),
            price=3,
            is_active=False,
        )
        cls.period_active = Period.objects.create(
            name="random_period_active",
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(weeks=4),
            price=3,
            is_active=True,
        )
        cls.time_slot = TimeSlot.objects.create(
            name="evening_time_slot",
            period=cls.period,
            price=3,
            start_time=LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 8)),
            end_time=LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 12)),
        )
        cls.time_slot.users.set([cls.admin, cls.user])
        cls.time_slot_active = TimeSlot.objects.create(
            name="evening_time_slot_active",
            period=cls.period_active,
            price=3,
            start_time=LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 18)),
            end_time=LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 22)),
        )

    def test_create(self):
        """
        Ensure we can create a timeslot if user has permission.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[self.period.id]),
            'price': '10.00',  # Will use Period's price if not provided
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 12)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 16)),
            'users': [reverse('user-detail', args=[self.user.id])]
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'id': 3,
            'end_time': data['end_time'].isoformat(),
            'name': 'random_time_slot',
            'price': '10.00',
            'start_time': data['start_time'].isoformat(),
            'url': 'http://testserver/time_slots/3',
            'period': 'http://testserver/periods/1',
            'users': ['http://testserver/users/1']
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_no_price(self):
        """
        Ensure we can create a timeslot without providing a price.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[self.period.id]),
            # 'price': '10.00',  # Will use Period's price if not provided
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 12)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 16)),
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'id': 3,
            'end_time': data['end_time'].isoformat(),
            'name': 'random_time_slot',
            'price': '3.00',
            'start_time': data['start_time'].isoformat(),
            'url': 'http://testserver/time_slots/3',
            'period': 'http://testserver/periods/1',
            'users': []
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_without_permission(self):
        """
        Ensure we can't create a timeslot if user has no permission.
        """
        self.client.force_authenticate(user=self.user)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[self.period.id]),
            # 'price': '10.00',  # Will use Period's price if not provided
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 12)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 16)),
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'detail': 'You do not have permission to perform this action.'
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_overlapping(self):
        """
        Ensure we can't create overlapping timeslot in the same period.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[self.period.id]),
            'price': '10.00',  # Will use Period's price if not provided
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 11)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 15)),
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'detail': [
                'An existing timeslot overlaps with the provided start_time '
                'and end_time.'
            ]
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_overlapping_user(self):
        """
        Ensure we can't create timeslot that has user thet has other timeslots
        are overlappong with this one.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[self.period_active.id]),
            'price': '10.00',  # Will use Period's price if not provided
            # start_time overlaps with self.timeslot
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 10)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 16)),
            'users': [reverse('user-detail', args=[self.admin.id])]
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'detail': [
                'The user has an overlapping timeslot.'
            ]
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_invalid_start_end(self):
        """
        Ensure we can't create timeslots with start_time greater than end_time.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[self.period.id]),
            'price': '10.00',  # Will use Period's price if not provided
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 14)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 10)),
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'end_time': ['End time must be later than start_time.'],
            'start_time': ['Start time must be earlier than end_time.']
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_inconsistent_day(self):
        """
        Ensure we can't create timeslots with start_time and end_time in
        different days.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[self.period.id]),
            'price': '10.00',  # Will use Period's price if not provided
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 14)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 16, 10)),
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'end_time': ['End time must be the same day as start_time.'],
            'start_time': ['Start time must be the same day as end_time.']
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_non_existent_period_user(self):
        """
        Ensure we can't create a timeslot with a non-existent period or user.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[999]),
            # 'price': '10.00',  # Will use Period's price if not provided
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 12)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 16)),
            'users': [reverse('user-detail', args=[999])],
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'period': ['Invalid hyperlink - Object does not exist.'],
            'users': ['Invalid hyperlink - Object does not exist.']
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_missing_field(self):
        """
        Ensure we can't create a timeslot when required field are missing.
        """
        self.client.force_authenticate(user=self.admin)

        data = {}

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'end_time': ['This field is required.'],
            'name': ['This field is required.'],
            'period': ['This field is required.'],
            'start_time': ['This field is required.']
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_blank_field(self):
        """
        Ensure we can't create a timeslot when required field are blank.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "",
            'period': None,
            'price': None,  # Will use Period's price if not provided
            'start_time': None,
            'end_time': None,
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'end_time': ['This field may not be null.'],
            'name': ['This field may not be blank.'],
            'period': ['This field may not be null.'],
            'start_time': ['This field may not be null.']
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_invalid_field(self):
        """
        Ensure we can't create a timeslot when required field are invalid.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "",
            'period': "123",
            'price': "",  # Will use Period's price if not provided
            'start_time': "",
            'end_time': "",
        }

        response = self.client.post(
            reverse('timeslot-list'),
            data,
            format='json',
        )

        content = {
            'end_time': [
                'Datetime has wrong format. Use one of these formats instead: '
                'YYYY-MM-DDThh:mm[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z].'
            ],
            'name': ['This field may not be blank.'],
            'period': ['Invalid hyperlink - No URL match.'],
            'price': ['A valid number is required.'],
            'start_time': [
                'Datetime has wrong format. Use one of these formats instead: '
                'YYYY-MM-DDThh:mm[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z].'
            ]
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update(self):
        """
        Ensure we can update a timeslot.
        """
        self.client.force_authenticate(user=self.admin)

        data = {
            'name': "random_time_slot",
            'period': reverse('period-detail', args=[self.period.id]),
            'price': '10.00',  # Will use Period's price if not provided
            'start_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 12)),
            'end_time': LOCAL_TIMEZONE.localize(datetime(2130, 1, 15, 16)),
        }

        response = self.client.put(
            reverse(
                'timeslot-detail',
                kwargs={'pk': 1},
            ),
            data,
            format='json',
        )

        content = {
            'id': 1,
            'end_time': data['end_time'].isoformat(),
            'name': 'random_time_slot',
            'price': '10.00',
            'start_time': data['start_time'].isoformat(),
            'url': 'http://testserver/time_slots/1',
            'period': 'http://testserver/periods/1',
            'users': ['http://testserver/users/1', 'http://testserver/users/2']
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete(self):
        """
        Ensure we can delete a timeslot.
        """
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            reverse(
                'timeslot-detail',
                kwargs={'pk': 1},
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_list(self):
        """
        Ensure we can list active timeslots as an unauthenticated user.
        """
        response = self.client.get(
            reverse('timeslot-list'),
            format='json',
        )

        data = json.loads(response.content)

        content = {
            'count': 1,
            'next': None,
            'previous': None,
            'results': [{
                'id': 2,
                'end_time': data['results'][0]['end_time'],
                'name': 'evening_time_slot_active',
                'price': '3.00',
                'start_time': data['results'][0]['start_time'],
                'url': 'http://testserver/time_slots/2',
                'period': 'http://testserver/periods/2',
                'users': []
            }]
        }

        self.assertEqual(data, content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_inactive(self):
        """
        Ensure we can list all timeslots as an admin user.
        """
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            reverse('timeslot-list'),
            format='json',
        )

        data = json.loads(response.content)

        content = {
            'count': 2,
            'next': None,
            'previous': None,
            'results': [{
                'id': 1,
                'end_time': data['results'][0]['end_time'],
                'name': 'evening_time_slot',
                'period': 'http://testserver/periods/1',
                'price': '3.00',
                'start_time': data['results'][0]['start_time'],
                'url': 'http://testserver/time_slots/1',
                'users': [
                    'http://testserver/users/1',
                    'http://testserver/users/2'
                ]
            }, {
                'id': 2,
                'end_time': data['results'][1]['end_time'],
                'name': 'evening_time_slot_active',
                'price': '3.00',
                'start_time': data['results'][1]['start_time'],
                'url': 'http://testserver/time_slots/2',
                'period': 'http://testserver/periods/2',
                'users': []
            }]
        }

        self.assertEqual(data, content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_filter_by_workplace(self):
        """
        Ensure we can list all timeslots linked to a workplace.
        """
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            reverse('timeslot-list') + "?period__workplace=1",
            format='json',
        )

        data = json.loads(response.content)

        content = {
            'count': 1,
            'next': None,
            'previous': None,
            'results': [{
                'id': 1,
                'end_time': data['results'][0]['end_time'],
                'name': 'evening_time_slot',
                'period': 'http://testserver/periods/1',
                'price': '3.00',
                'start_time': data['results'][0]['start_time'],
                'url': 'http://testserver/time_slots/1',
                'users': [
                    'http://testserver/users/1',
                    'http://testserver/users/2'
                ]
            }]
        }

        self.assertEqual(data, content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_filter_not_overiding_active(self):
        """
        Ensure we can list all timeslots linked to a workplace without
        overriding is_active default filtering.
        """
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            reverse('timeslot-list') + "?period__workplace=1",
            format='json',
        )

        data = json.loads(response.content)

        content = {
            'count': 0,
            'next': None,
            'previous': None,
            'results': []
        }

        self.assertEqual(data, content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_read(self):
        """
        Ensure we can read a timeslot as an unauthenticated user if it is
        active.
        """

        response = self.client.get(
            reverse(
                'timeslot-detail',
                kwargs={'pk': 2},
            ),
        )

        data = json.loads(response.content)

        content = {
            'id': 2,
            'end_time': data['end_time'],
            'name': 'evening_time_slot_active',
            'price': '3.00',
            'start_time': data['start_time'],
            'url': 'http://testserver/time_slots/2',
            'period': 'http://testserver/periods/2',
            'users': []
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_read_inactive_non_admin(self):
        """
        Ensure we can't read a timeslot as non_admin if it is inactive.
        """

        response = self.client.get(
            reverse(
                'timeslot-detail',
                kwargs={'pk': 1},
            ),
        )

        content = {'detail': 'Not found.'}

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_read_inactive(self):
        """
        Ensure we can read a timeslot as admin if it is inactive.
        """
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            reverse(
                'timeslot-detail',
                kwargs={'pk': 1},
            ),
        )

        data = json.loads(response.content)

        content = {
            'id': 1,
            'end_time': data['end_time'],
            'name': 'evening_time_slot',
            'period': 'http://testserver/periods/1',
            'price': '3.00',
            'start_time': data['start_time'],
            'url': 'http://testserver/time_slots/1',
            'users': [
                'http://testserver/users/1',
                'http://testserver/users/2'
            ]
        }

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_read_non_existent(self):
        """
        Ensure we get not found when asking for a period that doesn't exist.
        """

        response = self.client.get(
            reverse(
                'timeslot-detail',
                kwargs={'pk': 999},
            ),
        )

        content = {'detail': 'Not found.'}

        self.assertEqual(json.loads(response.content), content)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
