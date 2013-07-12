"""
The ``agar.django.templates`` module contains function(s) to render django templates 
in a manner that is aware of template loaders and dirs configured in the DJANGO_SETTINGS_MODULE
"""

def render_template_to_string(template_path, context={}):
    """
    A helper function that renders a Django template as a string in a
    manner that is aware of the loaders and dirs configured in the
    DJANGO_SETTINGS_MODULE.

    :param template_path: the template path relative to a configured module directory

    :param context: a dictionary of context attributes to referenced within the template
    """
    from django.template import loader
    return loader.render_to_string(template_path, context)

def render_template(response, template_path, context=None):
    """
    A helper function that renders django templates in a manner that is aware of the loaders 
    and dirs configured in the DJANGO_SETTINGS_MODULE

    :param template_path: the template path relative to a configured module directory

    :param context: a dictionary of context attributes to referenced within the template
    """
    if context is None:
        context = {}
    from django.template import loader
    response.out.write(loader.render_to_string(template_path, context))
