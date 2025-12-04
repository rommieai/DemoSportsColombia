"""Servicio para extraer colores dominantes de logos de equipos"""
from PIL import Image
import requests
from io import BytesIO
from collections import Counter
from typing import List, Tuple, Dict
import colorsys

class ColorExtractionService:
    """Extrae colores dominantes de imágenes de logos"""
    
    @staticmethod
    def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
        """Convierte RGB a HEX"""
        return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
    
    @staticmethod
    def is_grayscale(rgb: Tuple[int, int, int], threshold: int = 15) -> bool:
        """Detecta si un color es escala de grises (blanco/negro/gris)"""
        r, g, b = rgb
        return abs(r - g) < threshold and abs(g - b) < threshold and abs(r - b) < threshold
    
    @staticmethod
    def get_color_brightness(rgb: Tuple[int, int, int]) -> float:
        """Calcula el brillo de un color (0-1)"""
        return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
    
    @staticmethod
    def color_distance(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
        """Calcula la distancia entre dos colores"""
        return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5
    
    def extract_dominant_colors(
        self, 
        image_url: str, 
        num_colors: int = 2,
        max_colors_to_analyze: int = 10
    ) -> List[str]:
        """
        Extrae los colores dominantes de una imagen
        
        Args:
            image_url: URL de la imagen del logo
            num_colors: Número de colores a devolver (default: 2)
            max_colors_to_analyze: Cuántos colores analizar antes de filtrar
        
        Returns:
            Lista de colores en formato HEX (ej: ['#FF0000', '#0000FF'])
        """
        try:
            # Descargar imagen
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            
            # Abrir imagen con PIL
            img = Image.open(BytesIO(response.content))
            
            # Convertir a RGB si es necesario
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Redimensionar para acelerar el procesamiento (mantener aspect ratio)
            img.thumbnail((200, 200))
            
            # Obtener todos los píxeles
            pixels = list(img.getdata())
            
            # Contar frecuencia de colores
            color_counts = Counter(pixels)
            
            # Obtener los N colores más comunes
            most_common = color_counts.most_common(max_colors_to_analyze)
            
            # Filtrar colores (remover blancos, negros, muy similares)
            filtered_colors = []
            
            for color, count in most_common:
                # Ignorar colores muy claros (blancos) o muy oscuros (negros)
                brightness = self.get_color_brightness(color)
                
                # Saltar blancos (brightness > 0.9) y negros (brightness < 0.1)
                if brightness > 0.95 or brightness < 0.05:
                    continue
                
                # Verificar que no sea muy similar a colores ya seleccionados
                is_similar = False
                for existing_color in filtered_colors:
                    if self.color_distance(color, existing_color) < 50:  # Threshold de similitud
                        is_similar = True
                        break
                
                if not is_similar:
                    filtered_colors.append(color)
                
                # Si ya tenemos suficientes colores, parar
                if len(filtered_colors) >= num_colors:
                    break
            
            # Si no encontramos suficientes colores únicos, usar los más comunes
            if len(filtered_colors) < num_colors:
                for color, _ in most_common:
                    if color not in filtered_colors:
                        filtered_colors.append(color)
                    if len(filtered_colors) >= num_colors:
                        break
            
            # Convertir a HEX
            hex_colors = [self.rgb_to_hex(color) for color in filtered_colors[:num_colors]]
            
            return hex_colors
            
        except Exception as e:
            print(f"Error extrayendo colores de {image_url}: {str(e)}")
            # Colores por defecto en caso de error
            return ['#1E40AF', '#DC2626']  # Azul y rojo genéricos
    
    def get_team_colors(self, logo_url: str) -> Dict[str, str]:
        """
        Obtiene los dos colores principales de un logo de equipo
        
        Args:
            logo_url: URL del logo del equipo
        
        Returns:
            {"primary": "#HEX", "secondary": "#HEX"}
        """
        colors = self.extract_dominant_colors(logo_url, num_colors=2)
        
        return {
            "primary": colors[0] if len(colors) > 0 else "#1E40AF",
            "secondary": colors[1] if len(colors) > 1 else "#DC2626"
        }


# Función helper para usar en los endpoints
def get_team_colors_from_logo(logo_url: str) -> Dict[str, str]:
    """Helper function para extraer colores de un logo"""
    extractor = ColorExtractionService()
    return extractor.get_team_colors(logo_url)


# ===== EJEMPLO DE USO =====
if __name__ == "__main__":
    # Test con logos reales
    test_logos = [
        "https://media.api-sports.io/football/teams/65.png",  # Nottingham Forest
        "https://media.api-sports.io/football/teams/62.png",  # Sheffield Utd
    ]
    
    extractor = ColorExtractionService()
    
    for logo_url in test_logos:
        print(f"\nAnalizando: {logo_url}")
        colors = extractor.get_team_colors(logo_url)
        print(f"Colores: {colors}")