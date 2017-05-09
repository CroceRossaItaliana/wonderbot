from staging.cmd import file_write, file_delete, sudo_execute
from wonderbot.settings import NGINX_SITES_CONFIGURATION


class NginxConfigurationFile:

    def __init__(self, environment):
        self.environment = environment

    def get_contents(self):
        return """
# Configuration file created automatically using Wonderbot.
# Do not delete this file manually. Refer to the user manual on how
#  to delete an existing environment.
        
upstream django {
    server unix://%(socket)s
}

# configuration of the server
server {

    listen          8000;
    server_name     %(host_name)s;
    charset         utf-8;

    client_max_body_size 75M;

    location /static {
        alias %(static)s;
    }

    location / {
        uwsgi_pass  django;
        
        uwsgi_param  QUERY_STRING       $query_string;
        uwsgi_param  REQUEST_METHOD     $request_method;
        uwsgi_param  CONTENT_TYPE       $content_type;
        uwsgi_param  CONTENT_LENGTH     $content_length;
        uwsgi_param  REQUEST_URI        $request_uri;
        uwsgi_param  PATH_INFO          $document_uri;
        uwsgi_param  DOCUMENT_ROOT      $document_root;
        uwsgi_param  SERVER_PROTOCOL    $server_protocol;
        uwsgi_param  REQUEST_SCHEME     $scheme;
        uwsgi_param  HTTPS              $https if_not_empty;
        uwsgi_param  REMOTE_ADDR        $remote_addr;
        uwsgi_param  REMOTE_PORT        $remote_port;
        uwsgi_param  SERVER_PORT        $server_port;
        uwsgi_param  SERVER_NAME        $server_name;    
    }
}
        
        
        """ % {"socket": self.environment._get_uwsgi_socket_filename(),
               "host_name": self.environment.host(),
               "static": self.environment._get_nginx_static()}

    def save(self):
        contents = self.get_contents()
        path = self.get_path()
        file_write(path, contents)

    def delete(self):
        path = self.get_path()
        file_delete(path)

    def get_path(self):
        return "%s/%s.conf" % (NGINX_SITES_CONFIGURATION,
                               self.environment.name)


def _nginx_reload():
    return sudo_execute("service nginx reload")


def _nginx_restart():
    return sudo_execute("service nginx restart")

