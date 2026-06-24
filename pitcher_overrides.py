import os

def load_pitcher_overrides(filepath="pitcher_role_overrides.txt"):
    overrides = {}
    if not os.path.exists(filepath):
        return overrides
    with open(filepath, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                print(f"Warning: {filepath} line {i} is malformed (missing '='): {line!r}")
                continue
            name, _, role = line.partition('=')
            name = name.strip()
            role = role.strip().upper()
            if role not in ('SP', 'RP'):
                print(f"Warning: {filepath} line {i}: unrecognized role {role!r} for '{name}' (expected SP or RP)")
                continue
            overrides[name] = role
    return overrides
