flask_cors
==========

Simple Flask response processor to make server support of cross origin 
resource sharing easy.

Sample Usage:

    from flask import Flask
    import re
    
    app = Flask("Awesome API")
    
    # Some Allowed Origins
    allowed = (
        'http://localhost:9294', # Exact String Compare
        re.compile("^http([s]*):\/\/searchkea.com([\:\d]*)$"), # Match a regex
    )
    
    # Add Access Control Header
    cors = CrossOriginResourceSharing(app)
    cors.set_allowed_origins(*allowed)

Results:

    Access-Control-Allow-Headers: origin, x-requested-with, content-type, accept
    Access-Control-Allow-Origin: http://localhost:9294
    Access-Control-Allow-Credentials: True
    Access-Control-Allow-Methods: GET,POST,PUT,DELETE,OPTIONS
    Access-Control-Max-Age: 1728000