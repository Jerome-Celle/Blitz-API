from copy import copy
from datetime import timedelta
from decimal import Decimal, DecimalException

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers, status
from rest_framework.reverse import reverse
from rest_framework.validators import UniqueValidator

from blitz_api.serializers import UserSerializer
from blitz_api.services import (check_if_translated_field,
                                remove_translation_fields)
from store.exceptions import PaymentAPIError
from store.models import Order, OrderLine, PaymentProfile, Refund
from store.services import (charge_payment,
                            create_external_payment_profile,
                            create_external_card,
                            get_external_cards,
                            PAYSAFE_CARD_TYPE,
                            PAYSAFE_EXCEPTION,
                            refund_amount, )

from .fields import TimezoneField
from .models import (Picture, Reservation, Retirement, WaitQueue,
                     WaitQueueNotification, )

User = get_user_model()

TAX_RATE = settings.LOCAL_SETTINGS['SELLING_TAX']


class RetirementSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.ReadOnlyField()
    places_remaining = serializers.SerializerMethodField()
    total_reservations = serializers.ReadOnlyField()
    reservations = serializers.SerializerMethodField()
    reservations_canceled = serializers.SerializerMethodField()
    timezone = TimezoneField(
        required=False,
        help_text=_("Timezone of the workplace."),
    )
    name = serializers.CharField(
        required=False,
        validators=[UniqueValidator(queryset=Retirement.objects.all())],
    )
    name_fr = serializers.CharField(
        required=False,
        allow_null=True,
        validators=[UniqueValidator(queryset=Retirement.objects.all())],
    )
    name_en = serializers.CharField(
        required=False,
        allow_null=True,
        validators=[UniqueValidator(queryset=Retirement.objects.all())],
    )
    details = serializers.CharField(required=False, )
    country = serializers.CharField(required=False, )
    state_province = serializers.CharField(required=False, )
    city = serializers.CharField(required=False, )
    address_line1 = serializers.CharField(required=False, )

    # June 7th 2018
    # The SlugRelatedField serializer can't get a field's attributes.
    # Ex: It can't get the "url" attribute of Imagefield Picture.picture.url
    # So here is a workaround: a SerializerMethodField is used to manually get
    # picture urls. This works but is not as clean as it could be.
    # Note: this is a read-only field so it isn't used for Workplace creation.
    pictures = serializers.SerializerMethodField()

    def validate_refund_rate(self, value):
        if value > 100:
            raise serializers.ValidationError(_(
                "Refund rate must be between 0 and 100 (%)."
            ))
        return value

    def get_pictures(self, obj):
        request = self.context['request']
        picture_urls = [picture.picture.url for picture in obj.pictures.all()]
        return [request.build_absolute_uri(url) for url in picture_urls]

    def get_reservations(self, obj):
        reservation_ids = Reservation.objects.filter(
            is_active=True,
            retirement=obj,
        ).values_list(
            'id',
            flat=True,
        )
        return [
            reverse(
                'retirement:reservation-detail',
                args=[id],
                request=self.context['request'],
            ) for id in reservation_ids
        ]

    def get_reservations_canceled(self, obj):
        reservation_ids = Reservation.objects.filter(
            is_active=False,
            retirement=obj,
        ).values_list(
            'id',
            flat=True,
        )
        return [
            reverse(
                'retirement:reservation-detail',
                args=[id],
                request=self.context['request'],
            ) for id in reservation_ids
        ]

    def get_places_remaining(self, obj):
        seats = obj.seats
        reserved_seats = obj.reserved_seats
        reservations = obj.reservations.filter(is_active=True).count()
        return seats - reservations - reserved_seats

    def validate(self, attr):
        err = {}
        if not check_if_translated_field('name', attr):
            err['name'] = _("This field is required.")
        if not check_if_translated_field('details', attr):
            err['details'] = _("This field is required.")
        if not check_if_translated_field('country', attr):
            err['country'] = _("This field is required.")
        if not check_if_translated_field('state_province', attr):
            err['state_province'] = _("This field is required.")
        if not check_if_translated_field('city', attr):
            err['city'] = _("This field is required.")
        if not check_if_translated_field('address_line1', attr):
            err['address_line1'] = _("This field is required.")
        if not check_if_translated_field('timezone', attr):
            err['timezone'] = _("This field is required.")
        if not check_if_translated_field('postal_code', attr):
            err['postal_code'] = _("This field is required.")
        if not check_if_translated_field('seats', attr):
            err['seats'] = _("This field is required.")
        if not check_if_translated_field('price', attr):
            err['price'] = _("This field is required.")
        if not check_if_translated_field('start_time', attr):
            err['start_time'] = _("This field is required.")
        if not check_if_translated_field('end_time', attr):
            err['end_time'] = _("This field is required.")
        if not check_if_translated_field('min_day_refund', attr):
            err['min_day_refund'] = _("This field is required.")
        if not check_if_translated_field('refund_rate', attr):
            err['refund_rate'] = _("This field is required.")
        if not check_if_translated_field('min_day_exchange', attr):
            err['min_day_exchange'] = _("This field is required.")
        if not check_if_translated_field('is_active', attr):
            err['is_active'] = _("This field is required.")
        if not check_if_translated_field('accessibility', attr):
            err['accessibility'] = _("This field is required.")
        if err:
            raise serializers.ValidationError(err)
        return super(RetirementSerializer, self).validate(attr)

    def to_representation(self, instance):
        is_staff = self.context['request'].user.is_staff
        if self.context['view'].action == 'retrieve' and is_staff:
            self.fields['users'] = UserSerializer(many=True)
        data = super(RetirementSerializer, self).to_representation(instance)
        if is_staff:
            return data
        return remove_translation_fields(data)

    class Meta:
        model = Retirement
        exclude = ('deleted', )
        extra_kwargs = {
            'details': {
                'help_text': _("Description of the retirement.")
            },
            'name': {
                'help_text': _("Name of the retirement."),
                'validators':
                [UniqueValidator(queryset=Retirement.objects.all())],
            },
            'seats': {
                'required': False,
                'help_text': _("Number of available seats.")
            },
            'timezone': {
                'required': False,
            },
            'end_time': {
                'required': False,
            },
            'start_time': {
                'required': False,
            },
            'postal_code': {
                'required': False,
            },
            'refund_rate': {
                'required': False,
            },
            'min_day_exchange': {
                'required': False,
            },
            'min_day_refund': {
                'required': False,
            },
            'price': {
                'required': False,
            },
            'url': {
                'view_name': 'retirement:retirement-detail',
            },
        }


class PictureSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.ReadOnlyField()

    def to_representation(self, instance):
        data = super(PictureSerializer, self).to_representation(instance)
        if self.context['request'].user.is_staff:
            return data
        return remove_translation_fields(data)

    class Meta:
        model = Picture
        fields = '__all__'
        extra_kwargs = {
            'retirement': {
                'help_text': _("Retirement represented by the picture."),
                'view_name': 'retirement:retirement-detail',
            },
            'url': {
                'view_name': 'retirement:picture-detail',
            },
            'name': {
                'help_text': _("Name of the picture."),
            },
            'picture': {
                'help_text': _("File to upload."),
            }
        }


class ReservationSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.ReadOnlyField()
    # Custom names are needed to overcome an issue with DRF:
    # https://github.com/encode/django-rest-framework/issues/2719
    # I
    retirement_details = RetirementSerializer(
        read_only=True,
        source='retirement',
    )
    user_details = UserSerializer(
        read_only=True,
        source='user',
    )
    payment_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    single_use_token = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate(self, attrs):
        """Prevents overlapping reservations."""
        validated_data = super(ReservationSerializer, self).validate(attrs)

        action = self.context['view'].action

        # This validation is here instead of being in the 'update()' method
        # because we need to stop validation if improper fields are passed in
        # a partial update.
        if action == 'partial_update':
            # Only allow modification of is_present & retirement fields.
            is_invalid = validated_data.copy()
            is_invalid.pop('is_present', None)
            is_invalid.pop('retirement', None)
            is_invalid.pop('payment_token', None)
            is_invalid.pop('single_use_token', None)
            if is_invalid:
                raise serializers.ValidationError({
                    'non_field_errors': [
                        _("Only is_present and retirement can be updated. To "
                          "change other fields, delete this reservation and "
                          "create a new one.")
                    ]
                })
            return attrs

        # Generate a list of tuples containing start/end time of
        # existing reservations.
        start = validated_data['retirement'].start_time
        end = validated_data['retirement'].end_time
        active_reservations = Reservation.objects.filter(
            user=validated_data['user'],
            is_active=True,
        ).exclude(**validated_data).values_list(
            'retirement__start_time',
            'retirement__end_time',
        )

        for retirements in active_reservations:
            if max(retirements[0], start) < min(retirements[1], end):
                raise serializers.ValidationError({
                    'non_field_errors': [_(
                        "This reservation overlaps with another active "
                        "reservations for this user."
                    )]
                })
        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        user = instance.user
        payment_token = validated_data.pop('payment_token', None)
        single_use_token = validated_data.pop('single_use_token', None)
        need_transaction = False
        need_refund = False
        amount = 0
        profile = PaymentProfile.objects.filter(owner=user).first()
        instance_pk = instance.pk
        current_retirement = instance.retirement

        if not self.context['request'].user.is_staff:
            validated_data.pop('is_present', None)

        if (self.context['view'].action == 'partial_update'
                and validated_data.get('retirement')):
            if instance.order_line.quantity > 1:
                raise serializers.ValidationError({
                    'non_field_errors': [_(
                        "The order containing this reservation has a quantity "
                        "bigger than 1. Please contact the support team."
                    )]
                })
            respects_minimum_days = (
                (instance.retirement.start_time - timezone.now()) >=
                timedelta(days=instance.retirement.min_day_exchange))
            if instance.retirement.price < validated_data['retirement'].price:
                need_transaction = True
                amount = validated_data[
                    'retirement'
                ].price - instance.retirement.price
                if not (payment_token or single_use_token):
                    raise serializers.ValidationError({
                        'non_field_errors': [_(
                            "The new retirement is more expensive than the "
                            "current one. Provide a payment_token or "
                            "single_use_token to charge the balance."
                        )]
                    })
            if instance.retirement.price > validated_data['retirement'].price:
                need_refund = True
                amount = instance.retirement.price - validated_data[
                    'retirement'
                ].price
            if instance.retirement == validated_data['retirement']:
                raise serializers.ValidationError({
                    'retirement': [_(
                        "That retirement is already assigned to this object."
                    )]
                })
            if not respects_minimum_days:
                raise serializers.ValidationError({
                    'non_field_errors': [_(
                        "Maximum exchange date exceeded."
                    )]
                })
            if need_transaction:
                if single_use_token and not profile:
                    # Create external profile
                    try:
                        create_profile_res = create_external_payment_profile(
                            user
                        )
                    except PaymentAPIError as err:
                        raise serializers.ValidationError({
                            'message': err
                        })
                    # Create local profile
                    profile = PaymentProfile.objects.create(
                        name="Paysafe",
                        owner=user,
                        external_api_id=create_profile_res.json()['id'],
                        external_api_url='{0}{1}'.format(
                            create_profile_res.url,
                            create_profile_res.json()['id']
                        )
                    )
            # Generate a list of tuples containing start/end time of
            # existing reservations.
            start = validated_data['retirement'].start_time
            end = validated_data['retirement'].end_time
            active_reservations = Reservation.objects.filter(
                user=user,
                is_active=True,
            ).exclude(pk=instance.pk).values_list(
                'retirement__start_time',
                'retirement__end_time',
            )

            for retirements in active_reservations:
                if max(retirements[0], start) < min(retirements[1], end):
                    raise serializers.ValidationError({
                        'non_field_errors': [_(
                            "This reservation overlaps with another active "
                            "reservations for this user."
                        )]
                    })
            with transaction.atomic():
                if need_transaction:
                    order = Order.objects.create(
                        user=user,
                        transaction_date=timezone.now(),
                        authorization_id=1,
                        settlement_id=1,
                    )
                    orderline = OrderLine.objects.create(
                        order=order,
                        quantity=1,
                        content_type=ContentType.objects.get_for_model(
                            Retirement
                        ),
                        object_id=validated_data['retirement'].id
                    )
                    refund_value = instance.retirement.price * (Decimal(
                        TAX_RATE) + 1)
                    refund_instance = Refund.objects.create(
                        orderline=instance.order_line,
                        refund_date=timezone.now(),
                        amount=refund_value,
                        details="Exchange retirement {0} for "
                                "retirement {1}".format(
                                    str(instance.retirement),
                                    str(validated_data['retirement'])
                                ),
                    )
                    tax = round(amount * Decimal(TAX_RATE), 2)
                    amount *= Decimal(TAX_RATE + 1)
                    amount = round(amount * 100, 2)
                    retirement = validated_data['retirement']
                    user_waiting = retirement.wait_queue.filter(user=user)
                    if not (((retirement.seats - retirement.total_reservations
                              - retirement.reserved_seats) > 0) or
                            (retirement.reserved_seats
                             and WaitQueueNotification.objects.filter(
                                 user=user, retirement=retirement))):
                        raise serializers.ValidationError({
                            'non_field_errors': [_(
                                "There are no places left in the requested "
                                "retirement."
                            )]
                        })
                    if user_waiting:
                        user_waiting.delete()

                    if need_transaction and payment_token and int(amount):
                        # Charge the order with the external payment API
                        try:
                            charge_response = charge_payment(
                                int(amount),
                                payment_token,
                                str(order.id)
                            )
                        except PaymentAPIError as err:
                            raise serializers.ValidationError({
                                'message': err
                            })

                    elif need_transaction and single_use_token and int(amount):
                        # Add card to the external profile & charge user
                        try:
                            card_create_response = create_external_card(
                                profile.external_api_id,
                                single_use_token
                            )
                            charge_response = charge_payment(
                                int(amount),
                                card_create_response.json()['paymentToken'],
                                str(order.id)
                            )
                        except PaymentAPIError as err:
                            raise serializers.ValidationError({
                                'message': err
                            })
                    charge_res_content = charge_response.json()
                    order.authorization_id = charge_res_content['id']
                    order.settlement_id = charge_res_content['settlements'][0][
                        'id'
                    ]
                    order.reference_number = charge_res_content[
                        'merchantRefNum'
                    ]
                    order.save()
                    validated_data['order_line'] = orderline

                    # Here, the 'details' key is used to provide details of the
                    #  item to the email template.
                    # As of now, only 'retirement' objects have the
                    # 'email_content' key that is used here. There is surely a
                    # better way to handle that logic that will be more
                    # generic.
                    items = [
                        {
                            'price': orderline.content_object.price,
                            'name': "{0}: {1}".format(
                                str(orderline.content_type),
                                orderline.content_object.name
                            ),
                        }
                    ]

                    # Send order confirmation email
                    merge_data = {
                        'STATUS': "APPROUVÉE",
                        'CARD_NUMBER':
                        charge_res_content['card']['lastDigits'],
                        'CARD_TYPE': PAYSAFE_CARD_TYPE[
                            charge_res_content['card']['type']
                        ],
                        'DATETIME': timezone.localtime().strftime("%x %X"),
                        'ORDER_ID': order.id,
                        'CUSTOMER_NAME':
                            user.first_name + " " + user.last_name,
                        'CUSTOMER_EMAIL': user.email,
                        'CUSTOMER_NUMBER': user.id,
                        'AUTHORIZATION': order.authorization_id,
                        'TYPE': "Achat",
                        'ITEM_LIST': items,
                        'TAX': tax,
                        'DISCOUNT': instance.retirement.price,
                        'COUPON': {'code': _("Échange")},
                        'SUBTOTAL': round(amount / 100 - tax, 2),
                        'COST': round(Decimal(amount) / 100, 2),
                    }

                    plain_msg = render_to_string("invoice.txt", merge_data)
                    msg_html = render_to_string("invoice.html", merge_data)

                    send_mail(
                        "Confirmation d'achat",
                        plain_msg,
                        settings.DEFAULT_FROM_EMAIL,
                        [order.user.email],
                        html_message=msg_html,
                    )
                if need_refund:
                    tax = round(amount * Decimal(TAX_RATE), 2)
                    amount *= Decimal(TAX_RATE + 1)
                    amount = round(amount * 100, 2)
                    retirement = validated_data['retirement']
                    user_waiting = retirement.wait_queue.filter(user=user)
                    if not (((retirement.seats - retirement.total_reservations
                              - retirement.reserved_seats) > 0) or
                            (retirement.reserved_seats
                             and WaitQueueNotification.objects.filter(
                                 user=user, retirement=retirement))):
                        raise serializers.ValidationError({
                            'non_field_errors': [_(
                                "There are no places left in the requested "
                                "retirement."
                            )]
                        })
                    if user_waiting:
                        user_waiting.delete()

                    try:
                        refund_response = refund_amount(
                            instance.order_line.order.settlement_id,
                            int(amount)
                        )
                    except PaymentAPIError as err:
                        if str(err) == PAYSAFE_EXCEPTION['3406']:
                            raise serializers.ValidationError({
                                'non_field_errors': _(
                                    "The order has not been charged yet. "
                                    "Try again later."
                                )
                            })
                        raise serializers.ValidationError({
                            'message': str(err)
                        })

                    refund_instance = Refund.objects.create(
                        orderline=instance.order_line,
                        refund_date=timezone.now(),
                        amount=amount/100,
                        details="Exchange retirement {0} for "
                                "retirement {1}".format(
                                    str(instance.retirement),
                                    str(validated_data['retirement'])
                                ),
                    )

                    # Send the refund email
                    new_retirement = retirement
                    old_retirement = current_retirement

                    # Send refund confirmation email
                    merge_data = {
                        'DATETIME': timezone.localtime().strftime("%x %X"),
                        'ORDER_ID': instance.order_line.order.id,
                        'CUSTOMER_NAME':
                        user.first_name + " " + user.last_name,
                        'CUSTOMER_EMAIL': user.email,
                        'CUSTOMER_NUMBER': user.id,
                        'TYPE': "Remboursement",
                        'NEW_RETIREMENT': new_retirement,
                        'OLD_RETIREMENT': old_retirement,
                        'SUBTOTAL':
                        old_retirement.price - new_retirement.price,
                        'COST': round(amount/100, 2),
                        'TAX': round(Decimal(tax), 2),
                    }

                    plain_msg = render_to_string("refund.txt", merge_data)
                    msg_html = render_to_string("refund.html", merge_data)

                    send_mail(
                        "Confirmation de remboursement",
                        plain_msg,
                        settings.DEFAULT_FROM_EMAIL,
                        [user.email],
                        html_message=msg_html,
                    )

                canceled_reservation = instance
                canceled_reservation.pk = None
                canceled_reservation.save()
                instance = Reservation.objects.get(id=instance_pk)

            # End of atomic transaction

        instance = super(ReservationSerializer, self).update(
            instance,
            validated_data,
        )

        if validated_data.get('retirement'):
            retirement = instance.retirement
            new_retirement = retirement
            old_retirement = current_retirement

            # Send exchange confirmation email
            merge_data = {
                'DATETIME': timezone.localtime().strftime("%x %X"),
                'CUSTOMER_NAME': user.first_name + " " + user.last_name,
                'CUSTOMER_EMAIL': user.email,
                'CUSTOMER_NUMBER': user.id,
                'TYPE': "Échange",
                'NEW_RETIREMENT': new_retirement,
                'OLD_RETIREMENT': old_retirement,
            }

            plain_msg = render_to_string("exchange.txt", merge_data)
            msg_html = render_to_string("exchange.html", merge_data)

            send_mail(
                "Confirmation d'échange",
                plain_msg,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=msg_html,
            )

            # Create a copy of the reservation. This copy keeps track of
            # the exchange.
            canceled_reservation.is_active = False
            canceled_reservation.cancelation_reason = 'U'
            canceled_reservation.cancelation_action = 'E'
            canceled_reservation.cancelation_date = timezone.now()
            canceled_reservation.save()

            merge_data = {
                'RETIREMENT': retirement,
            }

            plain_msg = render_to_string(
                "retirement_info.txt",
                merge_data
            )
            msg_html = render_to_string(
                "retirement_info.html",
                merge_data
            )

            send_mail(
                "Confirmation d'inscription à la retraite",
                plain_msg,
                settings.DEFAULT_FROM_EMAIL,
                [instance.user.email],
                html_message=msg_html,
            )

        return Reservation.objects.get(id=instance_pk)

    class Meta:
        model = Reservation
        exclude = ('deleted', )
        extra_kwargs = {
            'retirement': {
                'help_text': _("Retirement represented by the picture."),
                'view_name': 'retirement:retirement-detail',
            },
            'is_active': {
                'required': True,
                'help_text': _("Whether the reservation is active or not."),
            },
            'url': {
                'view_name': 'retirement:reservation-detail',
            },
        }


class WaitQueueSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.ReadOnlyField()
    created_at = serializers.ReadOnlyField()

    def validate_user(self, obj):
        """
        Subscribe the authenticated user.
        If the authenticated user is an admin (is_staff), use the user provided
        in the request's 'user' field.
        """
        if self.context['request'].user.is_staff:
            return obj
        return self.context['request'].user

    class Meta:
        model = WaitQueue
        fields = '__all__'
        extra_kwargs = {
            'retirement': {
                'view_name': 'retirement:retirement-detail',
            },
            'url': {
                'view_name': 'retirement:waitqueue-detail',
            },
        }


class WaitQueueNotificationSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.ReadOnlyField()
    created_at = serializers.ReadOnlyField()

    class Meta:
        model = WaitQueue
        fields = '__all__'
        extra_kwargs = {
            'retirement': {
                'view_name': 'retirement:retirement-detail',
            },
            'url': {
                'view_name': 'retirement:waitqueuenotification-detail',
            },
        }
