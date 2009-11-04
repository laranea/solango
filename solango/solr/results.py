#
# Copyright 2008 Optaros, Inc.
#

import urllib

from xml.dom import minidom

from django.utils import simplejson

from solango.solr.facet import Facet, DateFacet
from solango.log import logger
from solango import conf 
from solango.registry import documents
from solango.solr import xmlutils
from solango.exceptions import SolrException


class Results(object):
    """
    Results
    -------
    Results instances parse Solr response JSON into Python objects. A Solr
    response contains a header section and, optionally, a result section.
    For update requests, the result section is generally omitted.

    See http://wiki.apache.org/solr/SolJSON
    """
    
    _json = {}
    header = None
    rows = 10
    start = 0
    url = None
    error = None
    error_code = None
    method = None
    
    def __init__(self, url, json):
        """
        Parses the provided XML body and initialize the header dictionary.
        """
        self.url = url
        self._json = simplejson.loads(json)
        self.header = self._json["responseHeader"]
    
    @property
    def status(self):
        """
        Returns the Solr response status code for this Results instance.
        """
        return self.header["status"]
    
    @property
    def success(self):
        """
        Returns true if this Results object indicates status of 0.
        """
        return self.status == 0
    
    @property
    def time(self):
        """
        Returns the server request time, in millis, for this Results instance.
        """
        return self.header["QTime"]



class ErrorResults(Results):
    """
    If the search results ends up in a massive error, we return this
    as a replacement. Avoids the UGLY "Invalid or missing XML" Error
    """
   
    def __init__(self, method, url, xml, error, code=None):
        self.method = method
        self.url = url
        self.xml = xml
        self.error = error
        self.error_code = code
 
    @property
    def status(self):
        return 1

    @property
    def time(self):
        return None


class SelectErrorResults(ErrorResults):
    """
    If the search results ends up in a massive error, we return this
    as a replacement. Avoids the UGLY "Invalid or missing XML" Error
    """
    count = None
    date_gap = None
    
    def __init__(self, url, error, code=None):
        self.method = "select"
        self.url = url
        self.documents = []
        self.facets = []
        self.facet_dates = []
        self.highlighting ={}
        self.count = 0
        self.header ={}
        

class UpdateResults(Results):
    """
    Results for Solr update requests.
    """
    
    
    def __init__(self, xml):
        """
        Parses the provided XML body and initialize the header dictionary.
        """
        if not xml:
            raise ValueError, "Invalid or missing XML"
        
        doc = minidom.parseString(xml)
        
        header = xmlutils.get_child_node(doc.firstChild, "lst", "responseHeader")
        
        self.header = xmlutils.get_dictionary(header)
        
        doc.unlink()
    
class SelectResults(Results):
    """
    Results for Solr select requests.
    """
    
    count = None
    date_gap = None
    
    def __init__(self, url, json):
        """
        Parses the provided XML body, including documents, facets, and
        highlighting information.  See Results.__init__(self, xml).
        """
        Results.__init__(self, url, json)
        
        self.documents = []
        self.facets = [] 
        self.highlighting = {}
        
        self._parse_results()
        
        self._parse_facets()
        
        self._parse_highlighting()
        
    def _parse_header(self):
        self.rows = int(self.header['params']['rows'])
        self.start = int(self.header['params']['start'])
          
    def _parse_results(self):
        """
        Parse the results array into the documents list.  Each resulting
        document element is a dictionary. 
        """
        result = self._json.get("response", None)
        
        if not result:
            raise ValueError, "Results contained no result."
        
        self.count = result["numFound"]
        
        for d in result["docs"]:
            document = documents[d['model']](d)
            self.documents.append(document)
        
    def _parse_facets(self):
        """
        Parses the facet counts into this Result's facets list.
        """

        facets = self._json.get('facet_counts', None)
        
        if not facets:
            return None
        
        fields = facets.get("facet_fields", None)
        
        if not fields:
            return None
                    
        #exceptions = xmlutils.get_child_node(facets, 'str')
        
        #if exceptions:
        #    raise SolrException('There was a java exception:  %s' % exceptions.lastChild.wholeText)

        for name, values in fields.items():
            self.facets.append(Facet(name, values))
        
        params = self.header.get('params', None)
        if params is not None:
            self.date_gap = params.get('facet.date.gap', '+1YEAR') # default to a 1 year gap
        
        
        facet_dates = self._json.get("facet_dates", [])
        
        for facet_date in facet_dates:
            self.facets.append(DateFacet(facet_date, self.date_gap))
        
    def _parse_highlighting(self):
        """
        Parses the highlighting list into this Result's highlighting dictionary.
        Also iterate over this Result's documents, inserting highlighting
        elements to their owning documents.
        """
        self.highlighting = self._json.get("highlighting", None)
        
        if not self.highlighting:
            return None

        for d in self.documents:
            #TODO: Ugly
            model_key = conf.SEARCH_SEPARATOR.join([d.fields['model'].value, d.pk_field.value])
            for key, value in self.highlighting[model_key].items():
                d.highlight += ' ' + ' '.join(value)
                d.fields[key].highlight = ' '.join(value)

