"""The giftee key: who a list is *for*, as one opaque string.

A giftee is derived from a list's three columns and is never its own row
(ADR 0006). This module is the only place that knows the key's format — the
client receives keys on `giftees[]` and on each shopping item and sends one
back on a write, and never builds or reads inside one.

Three shapes, one per way a list can be "for" someone:

| List state               | Key                              |
|--------------------------|----------------------------------|
| Neither marked           | `owner:{owner_id}`               |
| `account_person_id` set  | `person:{account_person_id}`     |
| `recipient_name` set     | `absent:{owner_id}:{name_b64}`   |

`name_b64` is the recipient name, UTF-8, base64url **without padding**, so a
name with a space, a slash or a dot is still one URL path segment and the key
needs no escaping on the wire.
"""
import base64
import binascii
from dataclasses import dataclass
from typing import Literal

Kind = Literal["owner", "person", "absent"]

OWNER = "owner"
PERSON = "person"
ABSENT = "absent"


@dataclass(frozen=True)
class GifteeRef:
    """The three facts a giftee is identified by (decision 1).

    `owner_id` is None for a `person` key: the key carries the person's id
    alone, and the owner is resolved from the list the giftee is found on. The
    service never stores a ref parsed from a key — it stores the triple of the
    list it matched, which always has all three.
    """

    owner_id: int | None
    account_person_id: int | None
    recipient_name: str | None

    @property
    def kind(self) -> Kind:
        if self.account_person_id is not None:
            return PERSON
        if self.recipient_name is not None:
            return ABSENT
        return OWNER


def _encode_name(name: str) -> str:
    return base64.urlsafe_b64encode(name.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_name(encoded: str) -> str:
    if not encoded:
        raise ValueError("Empty recipient name in giftee key.")
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        # Strict: the default decoder silently drops characters outside the
        # alphabet, which would turn garbage into an empty name.
        name = base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("Malformed recipient name in giftee key.") from exc
    if not name:
        raise ValueError("Empty recipient name in giftee key.")
    return name


def key_for_triple(
    owner_id: int, account_person_id: int | None, recipient_name: str | None
) -> str:
    """The key for a list's three columns. Total: the columns are mutually
    exclusive already (invariant 7), so exactly one branch applies."""
    if account_person_id is not None:
        return f"{PERSON}:{account_person_id}"
    if recipient_name is not None:
        return f"{ABSENT}:{owner_id}:{_encode_name(recipient_name)}"
    return f"{OWNER}:{owner_id}"


def key_for(gift_list) -> str:
    """The key for a `GiftList` — or anything carrying its three columns."""
    return key_for_triple(
        gift_list.owner_id, gift_list.account_person_id, gift_list.recipient_name
    )


def kind_of(key: str) -> Kind:
    return parse_key(key).kind


def _int(segment: str) -> int:
    if not segment.isdigit():
        raise ValueError("Malformed id in giftee key.")
    return int(segment)


def parse_key(key: str) -> GifteeRef:
    """Validate a key and split it into its parts. Raises `ValueError` on
    anything malformed — the service turns that into a 400."""
    parts = key.split(":")
    if parts[0] == OWNER and len(parts) == 2:
        return GifteeRef(_int(parts[1]), None, None)
    if parts[0] == PERSON and len(parts) == 2:
        return GifteeRef(None, _int(parts[1]), None)
    if parts[0] == ABSENT and len(parts) == 3:
        return GifteeRef(_int(parts[1]), None, _decode_name(parts[2]))
    raise ValueError(f"Malformed giftee key: {key!r}")
