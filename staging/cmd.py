
def bash_execute(command, stdout=None, stderr=None, cwd=None, venv=None):
    if venv:
        command = "source %s/bin/activate &&" % (venv, command)

    if cwd:
        command = "cd %s && %s" % (cwd, command)

    pass


def sudo_execute(command, **kwargs):
    command = "sudo %s" % command
    return bash_execute(command, **kwargs)


def file_delete(filename, **kwargs):
    command = "rm %s" % filename
    return bash_execute(command, **kwargs)


def file_write(filename, contents, mode="wt"):
    with open(filename, mode=mode) as f:
        return f.write(contents)


def dir_delete(path, **kwargs):
    command = "rm -rf %s" % path
    return bash_execute(command, **kwargs)


def dir_create(path, **kwargs):
    command = "mkdir %s" % path
    return bash_execute(command, **kwargs)
