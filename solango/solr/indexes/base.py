
from solango.deferred import defer
from solango.solr.connection import SearchWrapper
from solango.solr.query import Query

from solango import conf

class Index(object):
    """
    Solr Index
    """
    name = "default_index"
    update_url = ""
    select_urls = ()
    
    _connection = None
    
    def __init__(self, name=None, update_url=conf.SEARCH_UPDATE_URL, 
                 select_urls=conf.SEARCH_SELECT_URLS,
                 ping_urls=conf.SEARCH_PING_URLS,):
        
        if name is not None:
            self.name = name
        self.update_url = update_url
        self.select_urls = select_urls
        self.ping_urls = ping_urls
    
    def get_document(self, instance):
        from solango import documents
        return documents.get_document(instance)
    
    @property
    def connection(self):
        """Lazy Init a Collection """
        if self._connection is None:
            self._connection = SearchWrapper(self.update_url, 
                                             self.select_urls,
                                             self.ping_urls)
        return self._connection
    
    def query(self, initial=None, **kwargs):
        """
        Creates a default query.
        """
        default_initial = conf.SEARCH_FACET_PARAMS
        default_initial.extend(conf.SEARCH_HL_PARAMS)
        default = Query(default_initial , sort=conf.SEARCH_SORT_PARAMS.keys())
        
        query = Query(initial, **kwargs)
        
        default.merge(query)
        
        return default
            
    def ping(self):
        return self.connection.is_available()

    def optimize(self):
        return self.connection.optimize()
    
    def commit(self):
        return self.connection.commit()
    
    def add(self, doc, commit=True):
        return self.connection.add(doc.to_add_xml(), commit)
    
    def delete(self, doc, commit=True):
        return self.connection.delete(doc.to_delete_xml(), commit)
    
    def delete_all(self, commit=True):
        return self.connection.delete_all(commit)
    
    def delete_by_query(self, query, commit=True):
        return self.connection.delete_by_query(query, commit)

    def select(self, initial=None, **kwargs):
        if isinstance(initial, Query):
            query= initial
        else:
            query = self.query(initial, **kwargs)
        return self.connection.select(query)
    
    
    def reindex(self, model, doc, batch_size=50):
        start = 0
        stop = batch_size
        xml = ""
        
        while(1):
            qs = model._default_manager.all()[start:stop]
            for i in qs:
                xml += doc(i).to_add_xml()
            
            if not xml:
                break
            
            results = self.connection.add(xml)
            
            for result in results:
                if not result.success:
                    self.defer("add", result.xml, error=result.error)

            xml = ""
            
            start = stop + 1
            stop = start + batch_size

    def post_save(self, sender, instance, **kwargs):
        doc = documents.get_document(instance)
        self.add(doc)
    
    def post_delete(self, sender, instance, **kwargs):
        doc = documents.get_document(instance)
        self.delete(doc)

    def defer(self, method, xml, doc_pk=None, error=None):
        defer.add(method, xml, doc_pk, error)
        
        