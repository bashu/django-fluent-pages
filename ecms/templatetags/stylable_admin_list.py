"""
A stylable admin_list

This is a rewritten version of ``mptt/templatetags/mptt_admin.py`` which allows
more styling of the admin list throughout the ModelAdmin class.
By default, each column header will get a ``col-FIELD_NAME`` class,
allowing to set the widths of the column from CSS.

Furthermore, the ModelAdmin can add the property ``list_column_classes``
to the class, to define custom classes for a column.

This feature can be activated by simply extending the template stylable/admin/change_list.html
"""
from django.conf import settings
from django.contrib.admin.views.main import EMPTY_CHANGELIST_VALUE
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils import dateformat
from django.utils.html import escape, conditional_escape
from django.utils.text import capfirst
from django.utils.safestring import mark_safe
from django.utils.translation import get_date_formats
from django.utils.encoding import smart_unicode, force_unicode
from django.template import Library

from django.contrib.admin.templatetags.admin_list import _boolean_icon, result_headers

# While this is based on mptt/templatetags/mptt_admin.py,
# and django/contrib/admin/templatetags/admin_list.py,
# much has been changed, simplified, and refactored for clarity.
# What used to be one big method, is now split into several.


# Expose template tags
register = Library()

# Get app settings
MPTT_ADMIN_LEVEL_INDENT = getattr(settings, 'MPTT_ADMIN_LEVEL_INDENT', 10)


# Ideally the template name should be configurable too, provide a function instead of filename.
# For now, just reuse the existing admin template for the list contents.
@register.inclusion_tag("admin/change_list_results.html")
def stylable_result_list(cl):
    """
    Displays the headers and data list together
    """
    return {
        'cl': cl,
        'result_headers': list(stylable_result_headers(cl)),
        'results': list(stylable_results(cl))
    }


def stylable_result_headers(cl):
    """
    Reuse the existing result_headers() iterator,
    and add a `col-FIELD_NAME` class to the header.
    cl = The django ChangeList object
    """
    for field_name, header in zip(cl.list_display, result_headers(cl)):
        if header.get('class_attrib'):
            header['class_attrib'] = mark_safe(header['class_attrib'].replace('class="', 'class="col-%s ' % field_name))
        else:
            header['class_attrib'] = mark_safe(' class="col-%s"' % field_name)
        yield header


def stylable_results(cl):
    """
    Collect all rows to display
    """
    # yield was used for convenience, and kept as is.
    if cl.formset:
        for res, form in zip(cl.result_list, cl.formset.forms):
            yield list(stylable_items_for_result(cl, res, form))
    else:
        for res in cl.result_list:
            yield list(stylable_items_for_result(cl, res, None))


def stylable_items_for_result(cl, result, form):
    """
    Return an iterator which returns all columns to display in the list.
    This method is based on items_for_result(), yet completely refactored.
    """
    first = True
    pk = cl.lookup_opts.pk.attname

    # Read any custom properties
    list_column_classes = getattr(cl.model_admin, 'list_column_classes', {})

    # figure out which field to indent
    mptt_indent_field = _get_mptt_indent_field(cl, result)

    # Parse all fields to display
    for field_name in cl.list_display:
        row_attr = ''
        row_classes = []
        f = None

        # This is all standard stuff, refactored to separate methods.
        result_repr, row_classes = _get_column_repr(cl, result, field_name)
        if force_unicode(result_repr) == '':
            result_repr = mark_safe('&nbsp;')

        # Custom stuff, select row classes
        if field_name == mptt_indent_field:
            level = getattr(result, result._mptt_meta.level_attr)
            row_attr += ' style="padding-left:%spx"' % (5 + MPTT_ADMIN_LEVEL_INDENT * level)

        column_class = list_column_classes.get(field_name)
        if column_class:
            row_classes.append(column_class)

        if row_classes:
            row_attr += ' class="%s"' % ' '.join(row_classes)

        # Add the link tag to the first field, or use list_display_links if it's defined.
        if (first and not cl.list_display_links) or field_name in cl.list_display_links:
            table_tag = ('th' if first else 'td')
            first = False
            url = cl.url_for_result(result)

            link_attr = ''
            if cl.is_popup:
                # Convert the pk to something that can be used in Javascript.
                # Problem cases are long ints (23L) and non-ASCII strings.
                if cl.to_field:
                    attr = str(cl.to_field)
                else:
                    attr = pk
                value = result.serializable_value(attr)
                result_id = repr(force_unicode(value))[1:]
                link_attr += ' onclick="opener.dismissRelatedLookupPopup(window, %s); return false;"' % result_id

            yield mark_safe(u'<%s%s><a href="%s"%s>%s</a></%s>' % \
                (table_tag, row_attr, url, link_attr, conditional_escape(result_repr), table_tag))
        else:
            # By default the fields come from ModelAdmin.list_editable,
            # but if we pull the fields out of the form instead,
            # custom ModelAdmin instances can provide fields on a per request basis
            if form and field_name in form.fields:
                bf = form[field_name]
                result_repr = mark_safe(force_unicode(bf.errors) + force_unicode(bf))
            else:
                result_repr = conditional_escape(result_repr)

            yield mark_safe(u'<td%s>%s</td>' % (row_attr, result_repr))

    if form:
        yield mark_safe(u'<td>%s</td>' % force_unicode(form[cl.model._meta.pk.name]))


def _get_mptt_indent_field(cl, result):
    """
    Find the first field of the list, it will be indented visually.
    Allow working with normal models too.
    """
    if not hasattr(result, '_mptt_meta'):
        return None

    # Taken from mptt_items_for_result() in mptt/templatetags/mptt_admin.py
    mptt_indent_field = None
    for field_name in cl.list_display:
        try:
            f = cl.lookup_opts.get_field(field_name)
        except models.FieldDoesNotExist:
            if mptt_indent_field is None:
                attr = getattr(result, field_name, None)
                if callable(attr):
                    # first callable field, use this if we can't find any model fields
                    mptt_indent_field = field_name
        else:
            # first model field, use this one
            mptt_indent_field = field_name
            break
    return mptt_indent_field


def _get_column_repr(cl, result, field_name):
    """
    Get the string representation for a column item.
    This can be a model field, callable or property.
    """
    try:
        f = cl.lookup_opts.get_field(field_name)
    except models.FieldDoesNotExist:
        return _get_non_field_repr(cl, result, field_name)  # Field not found (maybe a function)
    else:
        return _get_field_repr(cl, result, f)  # Standard field


def _get_non_field_repr(cl, result, field_name):
    """
    Render the visual representation of a column
    which does not refer to a field in the model
    """
    # For non-field list_display values, the value is either:
    # - a method
    # - a attribute of the ModelAdmin
    # - a property or method of the model.
    try:
        if callable(field_name):
            attr = field_name
            value = attr(result)
        elif hasattr(cl.model_admin, field_name) and not field_name in ('__str__', '__unicode__'):
            attr = getattr(cl.model_admin, field_name)
            value = attr(result)
        else:
            attr = getattr(result, field_name)
            if callable(attr):
                value = attr()
            else:
                value = attr

        # Parse special attributes of the item
        allow_tags = getattr(attr, 'allow_tags', False)
        boolean = getattr(attr, 'boolean', False)
        if boolean:
            allow_tags = True
            result_repr = _boolean_icon(value)
        else:
            result_repr = smart_unicode(value)

    except (AttributeError, ObjectDoesNotExist):
        result_repr = EMPTY_CHANGELIST_VALUE
    else:
        # Strip HTML tags in the resulting text, except if the
        # function has an "allow_tags" attribute set to True.
        if not allow_tags:
            result_repr = escape(result_repr)
        else:
            result_repr = mark_safe(result_repr)

    return result_repr, None


def _get_field_repr(cl, result, f):
    """
    Render the visual representation of a column
    which refers to a field in the model
    """
    row_classes = []
    field_val = getattr(result, f.attname)
    result_repr = EMPTY_CHANGELIST_VALUE

    if isinstance(f.rel, models.ManyToOneRel):
        if field_val is not None:
            result_repr = escape(getattr(result, f.name))

    elif isinstance(f, models.DateField) \
      or isinstance(f, models.TimeField):
        # Dates and times are special: They're formatted in a certain way.
        if field_val:
            (date_format, datetime_format, time_format) = get_date_formats()
            if isinstance(f, models.DateTimeField):
                result_repr = capfirst(dateformat.format(field_val, datetime_format))
            elif isinstance(f, models.TimeField):
                result_repr = capfirst(dateformat.time_format(field_val, time_format))
            else:
                result_repr = capfirst(dateformat.format(field_val, date_format))
        row_classes += 'nowrap',

    elif isinstance(f, models.BooleanField) \
      or isinstance(f, models.NullBooleanField):
        # Booleans are special: using images.
        result_repr = _boolean_icon(field_val)

    elif isinstance(f, models.DecimalField):
        # DecimalFields are special: Zero-pad the decimals.
        if field_val is not None:
            result_repr = ('%%.%sf' % f.decimal_places) % field_val

    elif f.flatchoices:
        # Fields with choices are special: Use the representation of the choice.
        result_repr = dict(f.flatchoices).get(field_val, EMPTY_CHANGELIST_VALUE)

    else:
        result_repr = escape(field_val)

    return result_repr, row_classes
