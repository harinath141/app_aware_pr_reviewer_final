from datetime import datetime, timedelta, timezone

from app.auth import (ADMIN, USER, expiry_for, group_matches, is_expired, new_session_id,
                      role_from_memberof)

ADMIN_GROUP = "CONTEXTGUARD-ADMIN"
USER_GROUP = "CONTEXTGUARD-USER"

# --- group matching --------------------------------------------------------------------------

def test_bare_cn_matches_a_full_dn():
    dn = "CN=CONTEXTGUARD-ADMIN,OU=Groups,DC=corp,DC=example,DC=com"
    assert group_matches(dn, ADMIN_GROUP) is True

def test_matching_ignores_case_and_spacing():
    dn = "cn=contextguard-admin, ou=groups, dc=corp"
    assert group_matches(dn, "CONTEXTGUARD-ADMIN") is True

def test_group_in_a_different_ou_still_matches():
    # The point of matching on the CN: reorganising the directory must not silently revoke access.
    moved = "CN=CONTEXTGUARD-USER,OU=Retired,OU=Groups,DC=corp,DC=example,DC=com"
    assert group_matches(moved, USER_GROUP) is True

def test_a_different_group_does_not_match():
    other = "CN=CONTEXTGUARD-ADMINS,OU=Groups,DC=corp"
    assert group_matches(other, ADMIN_GROUP) is False

def test_a_substring_of_the_group_name_does_not_match():
    # A plain `in` check would wrongly accept this; matching is on the CN value, not a substring.
    sneaky = "CN=NOT-CONTEXTGUARD-ADMIN,OU=Groups,DC=corp"
    assert group_matches(sneaky, ADMIN_GROUP) is False

def test_a_configured_full_dn_is_compared_exactly():
    dn = "CN=CG-ADMIN,OU=Groups,DC=corp,DC=example,DC=com"
    assert group_matches(dn, "CN=CG-ADMIN,OU=Groups,DC=corp,DC=example,DC=com") is True
    assert group_matches(dn, "CN=CG-ADMIN,OU=Other,DC=corp,DC=example,DC=com") is False

def test_empty_values_never_match():
    assert group_matches("", ADMIN_GROUP) is False
    assert group_matches("CN=X", "") is False

# --- role assignment -------------------------------------------------------------------------

def test_admin_group_yields_admin():
    values = [f"CN={ADMIN_GROUP},OU=Groups,DC=corp"]
    assert role_from_memberof(values, ADMIN_GROUP, USER_GROUP) == ADMIN

def test_user_group_yields_user():
    values = [f"CN={USER_GROUP},OU=Groups,DC=corp"]
    assert role_from_memberof(values, ADMIN_GROUP, USER_GROUP) == USER

def test_being_in_both_groups_yields_admin():
    # Ordering of memberOf must not decide this.
    both = [f"CN={USER_GROUP},OU=Groups,DC=corp", f"CN={ADMIN_GROUP},OU=Groups,DC=corp"]
    assert role_from_memberof(both, ADMIN_GROUP, USER_GROUP) == ADMIN

def test_membership_of_neither_group_is_refused():
    # The case that matters: an authenticated directory account with no entitlement gets no role.
    assert role_from_memberof(["CN=Everyone,OU=Groups,DC=corp"], ADMIN_GROUP, USER_GROUP) is None

def test_no_groups_at_all_is_refused():
    assert role_from_memberof([], ADMIN_GROUP, USER_GROUP) is None
    assert role_from_memberof(None, ADMIN_GROUP, USER_GROUP) is None

# --- session arithmetic ----------------------------------------------------------------------

def test_session_ids_are_unique_and_long():
    ids = {new_session_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(len(value) >= 40 for value in ids)

def test_expiry_is_relative_to_now():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert expiry_for(now, 12) == now + timedelta(hours=12)

def test_expiry_never_lands_in_the_past():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert expiry_for(now, 0) > now
    assert expiry_for(now, -5) > now

def test_expiry_boundary_is_inclusive():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert is_expired(now, now) is True
    assert is_expired(now + timedelta(seconds=1), now) is False
    assert is_expired(now - timedelta(seconds=1), now) is True
