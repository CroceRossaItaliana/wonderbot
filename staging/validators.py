import string


def validate_environment_name(name):

    allowed_chars_start = string.ascii_lowercase
    allowed_chars_end = allowed_chars_start + string.digits
    allowed_chars = allowed_chars_start + string.digits + '-'
    minimum_length, maximum_length = 3, 16

    allowed_length = minimum_length <= len(name) <= maximum_length
    allowed_first_char = name[0] in allowed_chars_start
    allowed_last_char = name[-1:] in allowed_chars_end
    allowed_chars = all([character in allowed_chars for character in name])

    return allowed_length and \
           allowed_first_char and \
           allowed_last_char and \
           allowed_chars
