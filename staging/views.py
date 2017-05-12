import json

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from staging.models import Environment


@csrf_exempt
def github_hook(request):
    """
    Handles all GitHub requests.
    """

    if request.method != "POST":
        return HttpResponse("Ignoring non-POST requests.")

    # Security signature
    hub_signature = request.META["HTTP_X_HUB_SIGNATURE"]
    delivery = request.META["HTTP_X_GITHUB_DELIVERY"]

    # TODO check security!
    # See https://developer.github.com/webhooks/securing/

    event = request.META["HTTP_X_GITHUB_EVENT"]
    data = json.loads(request.body)

    if event == "pull_request":

        action = data["action"]
        number = data["number"]
        repo = data["pull_request"]["head"]["repo"]["ssh_url"]
        branch = data["pull_request"]["head"]["ref"]
        sha = data["pull_request"]["head"]["sha"]

        if action in ["opened", "reopened"]:
            return _do_opened_pull_request(number, repo, branch, sha)

        elif action == "closed":
            return _do_closed_pull_request(number)

        else:
            return HttpResponse("%s action on PR %d ignored." % (action, number),
                                content_type="text/plain")

    elif event == "push":

        repo = data["repository"]["ssh_url"]
        branch = data["ref"]
        sha = data["after"]

        return _do_push(repo, branch, sha)

    else:
        return HttpResponse("%s event ignored." % event,
                            content_type="text/plain")


def _do_opened_pull_request(number, repo, branch, sha):
    """
    React to a new pull request being opened.
    """

    # TODO check if repository is in list of allowed repositories!

    name = _environment_name_for_pr(number)
    environment = Environment(name=name, status=Environment.CREATING,
                              repository=repo, branch=branch, sha=sha)
    environment.save()
    environment.queue_for_creation()
    return HttpResponse("OK", content_type="text/plain")


def _do_closed_pull_request(number):
    """
    React to a pull request being closed.
    """
    name = _environment_name_for_pr(number)
    environment = Environment.objects.get(name=name)
    environment.queue_for_deletion()
    return HttpResponse("OK", content_type="text/plain")


def _do_push(repo, branch, sha):
    """
    React to commits being pushed to a branch.
    """
    environment = Environment.objects.filter(repository=repo, branch=branch).first()
    if not environment:
        return HttpResponse("Ignoring, no environment found for repo %s and branch %s." % (repo, branch),
                            content_type="text/plain")

    environment.sha = sha
    environment.save()
    environment.queue_for_update()
    return HttpResponse("OK", content_type="text/plain")


def _environment_name_for_pr(number):
    """
    Get an environment name for a pull request given its number.
    :param number: The PR number.
    :return: The name string.
    """
    return "pr-%d" % number
