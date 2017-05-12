import subprocess
import sys


def bash_execute(command, stdout=None, stderr=None, cwd=None, venv=None):

    if venv:
        command = ". %s/bin/activate && %s" % (venv, command)
    if cwd:
        command = "cd %s && %s" % (cwd, command)
    #stdout = stdout or sys.stdout
    #stderr = stderr or sys.stderr

    print("$ %s" % command)
    c = subprocess.call(command, shell=True,
                        stdout=stdout, stderr=stderr)
    return c


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
