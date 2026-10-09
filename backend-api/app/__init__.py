# package marker
import os

# Djassa -> Hossouko -> Fidelia renames: a deployment that still sets the old
# DJASSA_* or HOSSOUKO_* names keeps working. Runs before any app module reads
# its settings. A FIDELIA_* value, when set, always wins, then HOSSOUKO_*, then
# DJASSA_*. Remove once every environment uses the new names.
for _old in ("HOSSOUKO_", "DJASSA_"):
    for _name, _value in list(os.environ.items()):
        if _name.startswith(_old):
            os.environ.setdefault("FIDELIA_" + _name[len(_old):], _value)
