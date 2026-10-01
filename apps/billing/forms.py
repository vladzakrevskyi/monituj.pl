import re

from django import forms
from django.utils import timezone

from apps.billing import plans, registry
from apps.billing.invoicing import valid_nip
from apps.billing.models import BillingProfile, BillingProfileKind
from apps.common import nip as nip_rules

EARLY_START_LABEL = (
    "Żądam rozpoczęcia świadczenia usługi przed upływem 14 dni na odstąpienie "
    "od umowy. Wiem, że jeśli odstąpię od umowy, zapłacę za okres do chwili "
    "odstąpienia."
)


class PlanChoiceForm(forms.Form):
    plan = forms.ChoiceField(choices=[(p.code, p.name) for p in plans.PAID_PLANS])
    interval = forms.ChoiceField(
        choices=[(plans.MONTH, "Miesięcznie"), (plans.YEAR, "Rocznie")],
        initial=plans.MONTH,
    )

    def chosen(self):
        return plans.PLANS[self.cleaned_data["plan"]], self.cleaned_data["interval"]


class CheckoutForm(PlanChoiceForm):
    """The first order. Consumers (and sole traders buying outside their
    profession) have 14 days to withdraw; starting the service at once needs
    their explicit request - recorded in the audit log with the order."""

    early_start = forms.BooleanField(
        label=EARLY_START_LABEL,
        required=True,
        error_messages={
            "required": "Zaznacz zgodę na rozpoczęcie usługi, aby przejść do płatności."
        },
    )


POST_CODE_PL = re.compile(r"^\d{2}-\d{3}$")
# Form field -> register detail.
COMPANY_FIELDS = {
    "company_name": "name",
    "street": "street",
    "post_code": "post_code",
    "city": "city",
}


clean_nip = nip_rules.clean


class BillingProfileForm(forms.ModelForm):
    """Invoice details, checked before any payment. Buyers are in Poland
    only: a firm gives its NIP (checksum, the Ministry of Finance register)
    and its name and address come from GUS."""

    kind = forms.ChoiceField(
        label="Faktura na",
        choices=BillingProfileKind.choices,
        widget=forms.RadioSelect,
        initial=BillingProfileKind.PERSON,
    )

    class Meta:
        model = BillingProfile
        fields = [
            "kind",
            "company_name",
            "tax_id",
            "first_name",
            "last_name",
            "street",
            "post_code",
            "city",
        ]
        labels = {
            "company_name": "Nazwa firmy",
            "tax_id": "NIP",
            "first_name": "Imię",
            "last_name": "Nazwisko",
            "street": "Ulica i numer",
            "post_code": "Kod pocztowy",
            "city": "Miejscowość",
        }
        widgets = {
            "company_name": forms.TextInput(attrs={"autocomplete": "organization"}),
            "tax_id": forms.TextInput(attrs={"inputmode": "numeric"}),
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "street": forms.TextInput(attrs={"autocomplete": "address-line1"}),
            "post_code": forms.TextInput(attrs={"autocomplete": "postal-code"}),
            "city": forms.TextInput(attrs={"autocomplete": "address-level2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = None
        self.locked = []
        # Checked in clean(): what is required depends on the kind and on
        # what a register knew about the firm.
        for name in ("street", "post_code", "city"):
            self.fields[name].required = False
        # Editing: what came from the register stays locked on screen too.
        if self.instance.pk and self.instance.is_company:
            for name in self.instance.registry_fields:
                if name in self.fields:
                    self.fields[name].widget.attrs["readonly"] = True

    def _require(self, *names):
        for name in names:
            if not (self.cleaned_data.get(name) or "").strip():
                self.add_error(name, "To pole jest wymagane.")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == BillingProfileKind.COMPANY:
            cleaned["first_name"] = cleaned["last_name"] = ""
            self._require("tax_id")
            if cleaned.get("tax_id"):
                self._check_nip(cleaned)
            if not self.has_error("tax_id"):
                # Whatever the register lacks, the buyer types in.
                self._require(
                    *(name for name in COMPANY_FIELDS if name not in self.locked)
                )
        else:
            cleaned["company_name"] = cleaned["tax_id"] = ""
            self._require("first_name", "last_name", "street", "post_code", "city")
        post_code = (cleaned.get("post_code") or "").strip()
        if (
            "post_code" not in self.locked
            and post_code
            and not POST_CODE_PL.match(post_code)
        ):
            self.add_error("post_code", "Podaj kod pocztowy w formacie 00-000.")
        return cleaned

    def _check_nip(self, cleaned):
        nip = clean_nip(cleaned["tax_id"])
        cleaned["tax_id"] = nip
        if not valid_nip(nip):
            self.add_error(
                "tax_id", "Ten NIP jest nieprawidłowy - sprawdź, czy nie ma literówki."
            )
            return
        try:
            self.registry = registry.lookup(nip)
        except registry.FirmClosed:
            self.add_error("tax_id", "Według GUS ta firma zakończyła działalność.")
            return
        except registry.InvalidNip:
            self.add_error(
                "tax_id", "Ministerstwo Finansów nie zna tego NIP - sprawdź go."
            )
            return
        # What the register has is taken as is, whatever the browser sent;
        # only the missing details come from the form.
        for name, key in COMPANY_FIELDS.items():
            value = (self.registry or {}).get(key, "")
            if value:
                cleaned[name] = value
                self.locked.append(name)

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.tax_id = self.cleaned_data.get("tax_id", "")
        profile.country = "PL"
        found = self.registry or {}
        for name in ("company_name", "street", "post_code", "city"):
            setattr(profile, name, self.cleaned_data.get(name, ""))
        profile.registry_name = found.get("name", "")
        profile.registry_status = found.get("status", "")
        profile.registry_source = found.get("source", "")
        profile.registry_fields = list(self.locked)
        profile.registry_checked_at = timezone.now() if self.registry else None
        if commit:
            profile.save()
        return profile
