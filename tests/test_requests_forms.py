from datetime import date, time

import pytest

from apps.requests.forms import PublicRequestForm, RequestEditForm, RequestForm


def test_deadline_is_converted_to_end_of_day():
    form = RequestEditForm(
        data={
            "name": "R",
            "description": "",
            "deadline": "2026-10-05",
            "accept_terms": "on",
        }
    )

    assert form.is_valid(), form.errors
    deadline = form.cleaned_data["deadline"]

    assert deadline.date() == date(2026, 10, 5)
    assert deadline.time() == time(23, 59, 59, 999999)


def test_deadline_is_none_when_not_provided():
    form = RequestEditForm(data={"name": "R", "description": ""})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["deadline"] is None


def test_deadline_initial_value_renders_in_iso_format_for_html5_date_input():
    """<input type="date"> only accepts value="YYYY-MM-DD"; Django's default
    locale-aware DateInput formatting (e.g. "24.12.2026" for pl) is silently
    rejected by the browser, leaving the field looking empty on the edit
    form. The widget must pin format="%Y-%m-%d" regardless of locale."""
    form = RequestEditForm(initial={"deadline": date(2026, 12, 24)})

    rendered = str(form["deadline"])

    assert 'value="2026-12-24"' in rendered


def test_form_labels_are_polish_not_english():
    form = RequestEditForm()

    assert form.fields["name"].label == "Nazwa"
    assert form.fields["deadline"].label == "Termin"
    assert form.fields["reminders_enabled"].label == "Włącz automatyczne przypomnienia"
    for field in form.fields.values():
        assert field.label not in {
            "Name",
            "Deadline",
            "Description",
            "Reminders enabled",
        }


@pytest.mark.django_db
def test_request_form_valid_with_existing_client_and_no_new_client_email(
    user, client_record
):
    form = RequestForm(
        data={"client": client_record.pk, "name": "R", "description": ""}, owner=user
    )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_request_form_valid_with_new_client_email_and_no_existing_client(user):
    form = RequestForm(
        data={
            "new_client_name": "Nowy klient",
            "new_client_email": "nowy@example.com",
            "name": "R",
            "description": "",
        },
        owner=user,
    )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_request_form_invalid_when_neither_client_nor_new_client_email_given(user):
    form = RequestForm(data={"name": "R", "description": ""}, owner=user)

    assert not form.is_valid()
    assert "Wybierz istniejącego klienta lub podaj email nowego klienta." in str(
        form.errors
    )


@pytest.mark.django_db
def test_request_form_new_client_fields_have_polish_labels(user):
    form = RequestForm(owner=user)

    assert form.fields["new_client_name"].label == "Nazwa nowego klienta"
    assert form.fields["new_client_email"].label == "Email nowego klienta"
    assert form.fields["client"].label == "Istniejący klient"


@pytest.mark.django_db
def test_request_form_client_empty_choice_label_is_polish(user):
    """The client field became optional (for the quick-create-client flow),
    which makes Django render a blank choice using its default empty_label.
    Without an explicit Polish empty_label, Django 6.x's default
    "- Select an option -" leaks English into an otherwise Polish form."""
    form = RequestForm(owner=user)

    rendered = str(form["client"])

    assert "Select an option" not in rendered


def test_public_request_form_valid_with_client_name_and_email():
    form = PublicRequestForm(
        data={
            "sender_name": "Biuro Nowak",
            "sender_email": "biuro@example.com",
            "client_name": "Odbiorca",
            "client_email": "odbiorca@example.com",
            "name": "R",
            "description": "",
            "accept_terms": "on",
        }
    )

    assert form.is_valid(), form.errors


def test_public_request_form_requires_sender_and_recipient():
    form = PublicRequestForm(data={"name": "R", "description": ""})

    assert not form.is_valid()
    assert {"sender_name", "sender_email", "client_name", "client_email"} <= set(
        form.errors
    )


def test_public_request_form_rejects_invalid_client_email():
    form = PublicRequestForm(
        data={
            "client_name": "Odbiorca",
            "client_email": "not-an-email",
            "name": "R",
            "description": "",
        }
    )

    assert not form.is_valid()
    assert "Nieprawidłowy adres email." in str(form.errors["client_email"])


def test_public_request_form_has_no_client_selection_field():
    form = PublicRequestForm()

    assert "client" not in form.fields
    assert "new_client_name" not in form.fields
    assert "new_client_email" not in form.fields


def test_public_request_form_keeps_password_and_reminder_fields():
    form = PublicRequestForm()

    assert "password" in form.fields
    assert "reminders_enabled" in form.fields
    assert "reminder_frequency_days" in form.fields
    assert form.fields["client_name"].label == "Imię i nazwisko lub nazwa firmy"
    assert form.fields["client_email"].label == "Adres email odbiorcy"
    assert form.fields["sender_email"].label == "Twój adres email"


def test_public_request_form_deadline_converted_to_end_of_day():
    form = PublicRequestForm(
        data={
            "sender_name": "Biuro Nowak",
            "sender_email": "biuro@example.com",
            "client_name": "Odbiorca",
            "client_email": "odbiorca@example.com",
            "name": "R",
            "description": "",
            "deadline": "2026-10-05",
            "accept_terms": "on",
        }
    )

    assert form.is_valid(), form.errors
    deadline = form.cleaned_data["deadline"]
    assert deadline.date() == date(2026, 10, 5)
    assert deadline.time() == time(23, 59, 59, 999999)
