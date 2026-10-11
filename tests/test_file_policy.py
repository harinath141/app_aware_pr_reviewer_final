from app.file_policy import FilePolicy

def test_an_empty_policy_allows_everything():
    # The failure mode that would be worst: a repository nobody onboarded indexing zero files.
    policy = FilePolicy.from_patterns([], [])
    assert policy.is_empty
    assert policy.allows("src/main.py")
    assert policy.allows("anything/at/all.txt")

def test_blank_and_whitespace_patterns_are_dropped():
    policy = FilePolicy.from_patterns(["  ", "", "  src/*  "], ["   "])
    assert policy.include == ("src/*",)
    assert policy.exclude == ()

def test_patterns_are_de_duplicated_but_keep_their_order():
    policy = FilePolicy.from_patterns(["b/*", "a/*", "b/*"], [])
    assert policy.include == ("b/*", "a/*")

def test_exclude_wins_over_include():
    # The precedence rule: "everything except this" is the common intent.
    policy = FilePolicy.from_patterns(["src/*"], ["src/generated/*"])
    assert policy.allows("src/app.py") is True
    assert policy.allows("src/generated/schema.py") is False

def test_an_empty_include_list_means_everything_not_excluded():
    policy = FilePolicy.from_patterns([], ["docs/*"])
    assert policy.allows("src/main.py") is True
    assert policy.allows("docs/guide.md") is False

def test_a_non_empty_include_list_restricts_to_matches():
    policy = FilePolicy.from_patterns(["services/api/*"], [])
    assert policy.allows("services/api/handler.py") is True
    assert policy.allows("services/web/app.tsx") is False

def test_a_bare_directory_name_excludes_everything_beneath_it():
    policy = FilePolicy.from_patterns([], ["vendor"])
    assert policy.allows("vendor/lib.py") is False
    assert policy.allows("vendor") is False
    # But not a sibling that merely starts with the same letters.
    assert policy.allows("vendors/lib.py") is True

def test_a_trailing_slash_behaves_the_same_as_a_bare_name():
    policy = FilePolicy.from_patterns([], ["node_modules/"])
    assert policy.allows("node_modules/left-pad/index.js") is False

def test_wildcards_match_by_extension_at_any_depth():
    policy = FilePolicy.from_patterns([], ["*.min.js"])
    assert policy.allows("static/app.min.js") is False
    assert policy.allows("static/app.js") is True

def test_deep_paths_are_matched_against_the_whole_path():
    policy = FilePolicy.from_patterns([], ["*/generated/*"])
    assert policy.allows("pkg/generated/api.py") is False
    assert policy.allows("pkg/handwritten/api.py") is True
