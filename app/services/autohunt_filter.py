"""
AutoHunt post-fetch filters.

Pure Python — no Flask app context required. Importable standalone.
Called once per job description before a Job row is persisted.
"""
import re

# Drop roles that require non-English language proficiency
_LANGUAGE_BLOCK = re.compile(
    r'\b(fluent|native|proficient|required?|mandatory)\b.{0,40}'
    r'\b(german|french|spanish|dutch|portuguese|italian|mandarin|cantonese|'
    r'japanese|arabic|hindi|korean|russian|turkish|polish|swedish|norwegian|'
    r'danish|finnish|czech|romanian|hungarian|greek|hebrew|thai|vietnamese)\b',
    re.IGNORECASE,
)

# Drop roles that restrict to local residents / citizens without offering sponsorship
_VISA_BLOCK = re.compile(
    r'\b('
    r'must be (authoris|authoriz)ed to work|'
    r'no visa sponsorship|'
    r'citizens? only|'
    r'permanent residents? only|'
    r'right to work in \w[\w\s]{0,20} required|'
    r'work permit required|'
    r'legally (authoris|authoriz)ed to work'
    r')\b',
    re.IGNORECASE,
)

# Override — listing explicitly offers sponsorship; do NOT drop
_VISA_ALLOW = re.compile(
    r'\b('
    r'visa sponsorship (available|offered|considered)|'
    r'(we|company) (sponsor|provide|offer)s? visas?|'
    r'open to (relocation|sponsorship)|'
    r'(we )?(offer|provide|consider) visa sponsorship|'
    r'sponsorship (is |will be )?(available|considered)'
    r')\b',
    re.IGNORECASE,
)


def should_include(description: str) -> bool:
    """
    Return True if the job description passes AutoHunt filters.
    Return False if it requires a non-English language or restricts
    to local residents without offering visa sponsorship.
    """
    if not description:
        return True

    if _LANGUAGE_BLOCK.search(description):
        return False

    if _VISA_BLOCK.search(description):
        if not _VISA_ALLOW.search(description):
            return False

    return True
