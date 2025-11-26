# app/services/news_search_service.py
from typing import List, Optional
import logging
from pygooglenews import GoogleNews
from newspaper import Article
from datetime import datetime

logger = logging.getLogger(__name__)

class NewsSearchService:
    def __init__(self):
        # NO NECESITA API KEY!
        self.gn = GoogleNews(lang='es', country='CO')
    
    def search_google_news(self, query: str, max_results: int = 5) -> List[dict]:
        """
        Busca noticias reales en Google News - GRATIS, sin API key
        """
        try:
            # Buscar en Google News
            search_result = self.gn.search(query)
            
            if not search_result or 'entries' not in search_result:
                logger.warning(f"No news found for: {query}")
                return []
            
            noticias = []
            
            for entry in search_result['entries'][:max_results]:
                try:
                    # Extraer datos básicos
                    noticia = {
                        "title": entry.get('title', 'Sin título'),
                        "snippet": entry.get('summary', '')[:200],  # Primeros 200 chars
                        "link": entry.get('link', ''),
                        "date": self._format_date(entry.get('published', '')),
                        "source": entry.get('source', {}).get('title', 'Fuente desconocida')
                    }
                    
                    # Opcional: extraer contenido completo del artículo
                    # (esto toma más tiempo pero da mejor descripción)
                    if entry.get('link'):
                        try:
                            article = Article(entry['link'])
                            article.download()
                            article.parse()
                            noticia['snippet'] = article.text[:300]  # Primeros 300 chars
                        except:
                            pass  # Si falla, usamos el snippet de Google
                    
                    noticias.append(noticia)
                    
                except Exception as e:
                    logger.warning(f"Error parsing entry: {e}")
                    continue
            
            return noticias
            
        except Exception as e:
            logger.error(f"Error in search_google_news: {e}")
            return []
    
    def get_sports_news(self, max_results: int = 10) -> List[dict]:
        """
        Obtiene noticias deportivas de Colombia
        """
        try:
            top_sports = self.gn.topic_headlines('SPORTS')
            
            noticias = []
            for entry in top_sports['entries'][:max_results]:
                noticias.append({
                    "title": entry.get('title', ''),
                    "snippet": entry.get('summary', '')[:200],
                    "link": entry.get('link', ''),
                    "date": self._format_date(entry.get('published', '')),
                    "source": entry.get('source', {}).get('title', '')
                })
            
            return noticias
            
        except Exception as e:
            logger.error(f"Error getting sports news: {e}")
            return []
    
    def _format_date(self, date_str: str) -> str:
        """Formatea la fecha a algo más legible"""
        try:
            from dateutil import parser
            dt = parser.parse(date_str)
            return dt.strftime('%Y-%m-%d %H:%M')
        except:
            return date_str if date_str else 'Fecha desconocida'

