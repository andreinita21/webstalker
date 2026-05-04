from webstalker import diff, storage


def test_diff_text_basic_added_removed():
    a = "line1\nline2\nline3\n"
    b = "line1\nLINE2\nline3\nline4\n"
    lines, adds, dels = diff.diff_text(a, b)
    assert adds == 2  # LINE2, line4
    assert dels == 1  # line2

    kinds = [l.kind for l in lines]
    assert "added" in kinds
    assert "removed" in kinds


def test_diff_versions_uses_blob_reader():
    blobs: dict[str, bytes] = {}

    def reader(sha):
        return blobs[sha]

    a = b"<html>hello</html>"
    b = b"<html>hello world</html>"
    sha_a = storage.compute_sha256(a)
    sha_b = storage.compute_sha256(b)
    blobs[sha_a] = a
    blobs[sha_b] = b

    files = diff.diff_versions(
        [("index.html", sha_a, "text/html")],
        [("index.html", sha_b, "text/html")],
        reader,
    )
    assert len(files) == 1
    f = files[0]
    assert f.path == "index.html"
    assert f.is_binary is False
    assert f.additions >= 1
    assert f.deletions >= 1


def test_diff_versions_skips_unchanged_files():
    blobs: dict[str, bytes] = {}

    def reader(sha):
        return blobs[sha]

    same = b"unchanged"
    sha = storage.compute_sha256(same)
    blobs[sha] = same

    files = diff.diff_versions(
        [("a.html", sha, "text/html")],
        [("a.html", sha, "text/html")],
        reader,
    )
    assert files == []


def test_diff_versions_added_only_file():
    blobs: dict[str, bytes] = {}

    def reader(sha):
        return blobs[sha]

    new = b"new content"
    sha = storage.compute_sha256(new)
    blobs[sha] = new

    files = diff.diff_versions(
        [],
        [("new.html", sha, "text/html")],
        reader,
    )
    assert len(files) == 1
    assert files[0].old_blob is None
    assert files[0].new_blob == sha
    assert files[0].additions >= 1
