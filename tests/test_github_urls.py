from app.github_urls import graphql_url, oauth_urls, rest_base, web_host

GHES = "https://git.corp.example.com/api/v3"

def test_blank_means_github_dot_com():
    assert rest_base("") == "https://api.github.com"
    assert rest_base(None) == "https://api.github.com"
    assert web_host("") == "https://github.com"

def test_trailing_slash_is_normalised():
    assert rest_base("https://git.corp.example.com/api/v3/") == GHES

def test_enterprise_rest_and_web_are_split():
    assert rest_base(GHES) == GHES
    assert web_host(GHES) == "https://git.corp.example.com"

def test_enterprise_graphql_is_not_under_the_rest_prefix():
    # The whole reason this module exists: appending /graphql to the REST base yields
    # /api/v3/graphql, which 404s on Enterprise while every other call keeps working.
    assert graphql_url(GHES, "") == "https://git.corp.example.com/api/graphql"
    assert "/api/v3/graphql" not in graphql_url(GHES, "")

def test_github_dot_com_graphql_hangs_off_the_api_host():
    assert graphql_url("", "") == "https://api.github.com/graphql"

def test_explicit_graphql_override_wins():
    assert graphql_url(GHES, "https://gql.internal/graphql") == "https://gql.internal/graphql"

def test_oauth_sits_on_the_web_host_not_the_api_host():
    authorize, token = oauth_urls("")
    assert authorize == "https://github.com/login/oauth/authorize"
    assert token == "https://github.com/login/oauth/access_token"
    assert "api.github.com" not in authorize

def test_enterprise_oauth_sits_on_the_instance_host():
    authorize, token = oauth_urls(GHES)
    assert authorize == "https://git.corp.example.com/login/oauth/authorize"
    assert token == "https://git.corp.example.com/login/oauth/access_token"
