import random
import string


def random_alphanumerical_string(alphabet, l):
    return ''.join(random.SystemRandom().choice(alphabet) for _ in range(l))


def random_password(l):
    return random_alphanumerical_string(string.ascii_lowercase + string.ascii_uppercase + string.digits, l)


def random_username(l):
    return random_alphanumerical_string(string.ascii_lowercase, l)


def get_branch_name_from_ref(ref):
    if ref.count('/') < 2:
        return ref
    return ref.split('/')[2]
