from wonderbot.settings import DEFAULT_REPOSITORY, HOME_URL

import json
import requests


def github_token():
    """
    Tries to read a token from ~/.github_token and return it.
    Returns None if no token is found.
    """
    try:
        with open("~/.github_token", "rt") as f:
            return f.readline().rstrip("\n")
    except:
        return None


def github_commit_status(sha, state, description, url):
    token = github_token()
    if not token:
        return

    assert state in ('success', 'pending', 'error', 'failure')
    url = "https://api.github.com/repos/%s/statuses/%s" % (DEFAULT_REPOSITORY, sha)
    payload = json.dumps({"state": state,
                          "description": description,
                          "context": "wonderbot-pr",
                          "url": url})
    headers = {"Authorization": "token %s" % token,}
    requests.post(url, data=payload, headers=headers)


def github_pending(sha):
    github_commit_status(sha, "pending", "Wonderbot is updating the environment.", url=HOME_URL)


def github_finished(environment):
    github_commit_status(environment.sha, "success",
                         "Wonderbot has created a test environment.", url=environment.url())
