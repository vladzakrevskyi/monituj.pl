"""Existing questions get their conversation (QuestionMessage) from what the
item kept: the question, the follow-up (rejection_reason) and the latest
answer. An answer a follow-up used to overwrite can't be brought back."""

from datetime import timedelta

from django.db import migrations


def build_threads(apps, schema_editor):
    RequestItem = apps.get_model("requests", "RequestItem")
    QuestionMessage = apps.get_model("requests", "QuestionMessage")
    for item in RequestItem.objects.filter(kind="pytanie").select_related("request"):
        if QuestionMessage.objects.filter(item=item).exists():
            continue
        thread = [("nadawca", item.description, item.request.created_at)]
        answered = item.answered_at or item.updated_at
        if item.answer and item.status == "odrzucony":
            thread.append(("klient", item.answer, answered))
            if item.rejection_reason:
                thread.append(("nadawca", item.rejection_reason, item.updated_at))
        elif item.answer:
            if item.rejection_reason:
                before = answered - timedelta(seconds=1)
                thread.append(("nadawca", item.rejection_reason, before))
            thread.append(("klient", item.answer, answered))
        for author, text, at in thread:
            if not (text or "").strip():
                continue
            message = QuestionMessage.objects.create(item=item, author=author, text=text)
            # created_at is set on save (auto_now_add) - put the real time back.
            QuestionMessage.objects.filter(pk=message.pk).update(created_at=at)


class Migration(migrations.Migration):
    dependencies = [
        ("requests", "0012_questionmessage"),
    ]

    operations = [
        migrations.RunPython(build_threads, migrations.RunPython.noop),
    ]
