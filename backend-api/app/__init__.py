# package marker
import os

# Djassa -> Hossouko rename: a deployment that still sets the old DJASSA_* names
# keeps working. Runs before any app module reads its settings; a HOSSOUKO_*
# value, when set, always wins. Remove once every environment uses the new names.
for _name, _value in list(os.environ.items()):
    if _name.startswith("DJASSA_"):
        os.environ.setdefault("HOSSOUKO_" + _name[len("DJASSA_"):], _value)
