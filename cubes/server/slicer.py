# Werkzeug
from werkzeug.routing import Map, Rule
from werkzeug.wrappers import Request
from werkzeug.wsgi import ClosingIterator
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.wrappers import Response
import werkzeug.serving

# Package imports
import json
import sqlalchemy
import cubes

# Local imports
from utils import local, local_manager, url_map
import controllers
import search

rules = Map([
    Rule('/', endpoint = (controllers.ApplicationController, 'index')),
    Rule('/version', 
                        endpoint = (controllers.ApplicationController, 'version')),
    Rule('/model', 
                        endpoint = (controllers.ModelController, 'show')),
    Rule('/model/dimension/<string:name>',
                        endpoint = (controllers.ModelController, 'dimension')),
    Rule('/model/cube',
                        endpoint = (controllers.ModelController, 'get_default_cube')),
    Rule('/model/cube/<string:name>',
                        endpoint = (controllers.ModelController, 'get_cube')),
    Rule('/model/dimension/<string:name>/levels', 
                        endpoint = (controllers.ModelController, 'dimension_levels')),
    Rule('/model/dimension/<string:name>/level_names', 
                        endpoint = (controllers.ModelController, 'dimension_level_names')),
    Rule('/aggregate', 
                        endpoint = (controllers.AggregationController, 'aggregate')),
    Rule('/facts', 
                        endpoint = (controllers.AggregationController, 'facts')),
    Rule('/fact/<string:id>', 
                        endpoint = (controllers.AggregationController, 'fact')),
    Rule('/dimension/<string:dimension>', 
                        endpoint = (controllers.AggregationController, 'values')),
    Rule('/report', methods = ['POST'],
                        endpoint = (controllers.AggregationController, 'report')),
    Rule('/search',
                        endpoint = (search.SearchController, 'search'))
])

class Slicer(object):

    def __init__(self, config = None):
        """Create a WSGI server for providing OLAP web service.
        
        API:
            * ``/model`` - get model metadata
            * ``/model/dimension/dimension_name`` - get dimension metadata
            * ``/model/dimension/dimension_name/levels`` - get levels of default dimension hierarchy
            * ``/model/dimension/dimension_name/level_names`` - get just names of levels 
            * ``/aggregate`` - return aggregation result
        
        """
        
        local.application = self
        self.config = config

        self.dburl = config.get("db", "url")
        self.engine = sqlalchemy.create_engine(self.dburl)

        model_path = config.get("model", "path")
        try:
            self.model = cubes.load_model(model_path)
        except:
            if not model_path:
                model_path = 'unknown path'
            raise Exception("Unable to load model from %s" % model_path)
        
    def __call__(self, environ, start_response):
        local.application = self
        request = Request(environ)
        urls = rules.bind_to_environ(environ)
        
        try:
            endpoint, params = urls.match()

            (controller_class, action) = endpoint
            controller = controller_class(self.config)
            
            response = self.dispatch(controller, action, request, params)
        except HTTPException, e:
            response = e

        return ClosingIterator(response(environ, start_response),
                               [local_manager.cleanup])
        
    def dispatch(self, controller, action_name, request, params):

        controller.request = request
        controller.params = params
        controller.locale = params.get("lang")
        controller.engine = self.engine
        controller.master_model = self.model
        
        action = getattr(controller, action_name)

        controller.initialize()
        try:
            retval = action()
        finally:
            controller.finalize()

        return retval

    def error(self, message, exception):
        string = json.dumps({"error": {"message": message, "reason": str(exception)}})
        return Response(string, mimetype='application/json')
    
def run_server(config):
    """Run OLAP server with configuration specified in `config`"""
    if config.has_option("server", "host"):
        host = config.get("server", "host")
    else: 
        host = "localhost"

    if config.has_option("server", "port"):
        port = config.getint("server", "port")
    else:
        port = 5000

    if config.has_option("server", "reload"):
        use_reloader = config.getboolean("server", "reload")
    else:
        use_reloader = False

    application = Slicer(config)
    werkzeug.serving.run_simple(host, port, application, use_reloader = use_reloader)

