"""URL routing table for Artifact Registry (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.artifactregistry.responses import ArtifactRegistryResponse as R

_P = r"/v1/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)"
_REPO = _P + r"/repositories/(?P<repository>[^/]+)"
_PKG = _REPO + r"/packages/(?P<package>[^/]+)"
_VER = _PKG + r"/versions/(?P<version>[^/]+)"
_TAG = _PKG + r"/tags/(?P<tag>[^/]+)"
_FILE = _REPO + r"/files/(?P<file>[^/]+)"

url_bases = [r"https?://([a-z0-9-]+-)?artifactregistry\.googleapis\.com"]

url_paths = {
    # Long-running operation polling.
    f"GET {_P}/operations/(?P<operation>[^/]+)": R.get_operation,
    # Tags (nested under a package; list before the item routes).
    f"POST {_PKG}/tags": R.create_tag,
    f"GET {_PKG}/tags": R.list_tags,
    f"GET {_TAG}": R.get_tag,
    f"PATCH {_TAG}": R.update_tag,
    f"DELETE {_TAG}": R.delete_tag,
    # Versions.
    f"GET {_PKG}/versions": R.list_versions,
    f"GET {_VER}": R.get_version,
    f"DELETE {_VER}": R.delete_version,
    # Files.
    f"GET {_REPO}/files": R.list_files,
    f"GET {_FILE}": R.get_file,
    # Packages.
    f"GET {_REPO}/packages": R.list_packages,
    f"GET {_PKG}": R.get_package,
    f"DELETE {_PKG}": R.delete_package,
    # Repositories.
    f"POST {_P}/repositories": R.create_repository,
    f"GET {_P}/repositories": R.list_repositories,
    f"GET {_REPO}": R.get_repository,
    f"PATCH {_REPO}": R.update_repository,
    f"DELETE {_REPO}": R.delete_repository,
}
