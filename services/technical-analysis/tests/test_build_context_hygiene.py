"""Build-context hygiene guard for the technical-analysis service.

Two claims, both about what a ``docker build`` of this service is allowed to
carry into the image:

1. No ``*.bak`` file exists anywhere under the service directory.
2. ``.dockerignore`` excludes the ``*.bak`` glob.

WHY THIS GUARD EXISTS (P21-8, 2026-08-27)
-----------------------------------------
``app/main.py.bak`` sat beside the live ``app/main.py`` for nine months
(32,865 bytes, mtime 2025-11-10). It was runtime-inert -- nothing imports a
``.bak`` -- but the build context is not the import graph. This service's
Dockerfile copies ``app/`` wholesale and ``.dockerignore`` did not exclude
``*.bak``, so the stale file was copied into the image, where it shipped its
pre-fix CORS block: ``allow_origins=["*"]`` together with
``allow_credentials=True`` (``main.py.bak:91-92``). The live source closed
that hole in ``e091826`` and now sets ``allow_credentials=False``
(``app/main.py:236-237``).

A stale source file in a shipped layer is an information-disclosure surface
even when no process reads it, and this one is worse than an ordinary stale
file: it advertises a vulnerability the running code no longer has.

BOTH HALVES ARE REQUIRED, NEITHER SUBSTITUTES FOR THE OTHER
-----------------------------------------------------------
Deleting the file without adding the glob leaves the next ``.bak`` free to
enter the image. Adding the glob without deleting the file leaves the current
one in every image layer already built.

READ THIS BEFORE TRUSTING A GREEN RUN
-------------------------------------
Assertion 1 is **vacuous in CI and in any fresh clone**. Repo-root
``.gitignore:185`` excludes ``*.bak``, so no ``.bak`` file has ever been
tracked and none is materialised by a clone, a linked worktree checkout, or a
CI job. Its teeth are in the operator's own working copy -- which is exactly
where ``docker build`` runs from, and therefore exactly where the hazard
lives. A green result proves "this checkout is clean", not "the repository can
never carry one".

Assertion 2 is the half that holds in every environment, and it is what stops
the next ``.bak`` regardless of who created it. If you are tempted to delete
assertion 1 as always-green, delete this file instead of half of it -- a guard
that only checks the always-true half is worse than none, because it reports
coverage it does not have.

The ``.dockerignore`` change takes effect only on the next image build. Plan
21-09's phase gate performs that rebuild; until then the exclusion is declared
but not applied to the running container.
"""

from pathlib import Path

# Resolved from this file, not from a repo-root constant: this service's
# pytest.ini sets ``pythonpath = .`` and the suite runs from
# ``services/technical-analysis``, so there is no REPO_ROOT to anchor against.
SERVICE_ROOT = Path(__file__).resolve().parents[1]

DOCKERIGNORE_PATH = SERVICE_ROOT / ".dockerignore"

BAK_GLOB = "*.bak"

# Directories .dockerignore already excludes wholesale. A .bak inside one of
# them cannot reach the build context, so flagging it would report a finding
# that is not a hazard -- and ``logs/`` in a live working copy is large enough
# to make the walk slow. Everything else under the service is scanned.
#
# KNOWN NARROWING, stated rather than hidden: this set is pruned at ANY depth,
# while .dockerignore's ``logs/`` (no ``**/`` prefix) excludes only at the
# context root. A .bak under ``subdir/logs/`` would therefore enter the build
# context and this walk would skip it. Zero such paths exist today -- an
# unpruned ``find services/technical-analysis -name '*.bak'`` agrees with this
# walk -- but the gap is real and is the same "a detector that silently misses
# one fails GREEN" shape the module docstring warns about. Close it by
# prefixing the .dockerignore globs with ``**/``, not by widening this walk.
PRUNED_DIRS = frozenset(
    {".git", ".pytest_cache", "__pycache__", "htmlcov", "logs"}
)


def _bak_files(root: Path) -> list[Path]:
    """Every ``*.bak`` under ``root``, skipping the wholesale-excluded dirs."""
    found: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in PRUNED_DIRS:
                    stack.append(entry)
            elif entry.name.endswith(".bak"):
                found.append(entry)
    return found


def _dockerignore_globs(text: str) -> list[str]:
    """Non-comment, non-blank lines, stripped."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_no_bak_file_exists_under_the_service():
    """No stale ``.bak`` can be swept into a build context from this tree.

    Vacuous in CI (see the module docstring); load-bearing in the operator's
    working copy, which is where ``docker build`` actually reads from.
    """
    offenders = _bak_files(SERVICE_ROOT)

    assert offenders == [], (
        "stale .bak file(s) under the technical-analysis service: "
        + ", ".join(str(p.relative_to(SERVICE_ROOT)) for p in sorted(offenders))
        + ". A .bak is copied into the image by the Dockerfile's `COPY app/` "
        "and ships whatever pre-fix source it froze. Delete it; do not "
        "relocate it inside the service."
    )


def test_dockerignore_excludes_the_bak_glob():
    """The exclusion survives future edits to ``.dockerignore``.

    Asserted as an exact standalone line rather than a substring: ``*.bak``
    appearing only inside a comment would satisfy a naive ``in`` check while
    excluding nothing.
    """
    assert DOCKERIGNORE_PATH.is_file(), f"missing {DOCKERIGNORE_PATH}"

    globs = _dockerignore_globs(DOCKERIGNORE_PATH.read_text())

    assert BAK_GLOB in globs, (
        f"{BAK_GLOB} is not an active glob in .dockerignore (found: {globs}). "
        "Without it the next stale backup file enters the build context, "
        "which is how app/main.py.bak shipped a credentialed CORS wildcard "
        "for nine months."
    )

    # The pre-existing exclusions must survive alongside the new one -- a
    # rewrite that drops `logs/` reintroduces the tar failures this file was
    # created to prevent.
    for required in ("logs/", "tests/standalone/", "**/__pycache__/"):
        assert required in globs, (
            f"pre-existing .dockerignore glob {required!r} was dropped "
            f"(found: {globs})"
        )
