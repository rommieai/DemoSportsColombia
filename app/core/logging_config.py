"""
Configuración centralizada de logging para la aplicación
- Logs rotativos con límite de 200MB
- Formato detallado con timestamps
- Logs por nivel (INFO, DEBUG, ERROR)
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Directorio para logs
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

# Formato detallado para logs
LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-30s | "
    "%(funcName)-20s | Line %(lineno)-4d | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Configuración de tamaños
MAX_BYTES = 200 * 1024 * 1024  # 200 MB
BACKUP_COUNT = 5  # Mantener 5 archivos de backup


def setup_logging(level: int = logging.INFO):
    """
    Configura el sistema de logging de la aplicación
    
    Args:
        level: Nivel de logging (logging.DEBUG, logging.INFO, etc.)
    """
    
    # Crear formateador
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    
    # ============== ROOT LOGGER ==============
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Limpiar handlers existentes
    root_logger.handlers.clear()
    
    # ============== CONSOLE HANDLER ==============
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # ============== FILE HANDLERS ==============
    
    # 1. Handler para todos los logs (INFO y superior)
    all_logs_handler = RotatingFileHandler(
        filename=LOGS_DIR / "app.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8"
    )
    all_logs_handler.setLevel(logging.INFO)
    all_logs_handler.setFormatter(formatter)
    root_logger.addHandler(all_logs_handler)
    
    # 2. Handler solo para errores
    error_handler = RotatingFileHandler(
        filename=LOGS_DIR / "errors.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # 3. Handler para logs de rendimiento (timing)
    performance_handler = RotatingFileHandler(
        filename=LOGS_DIR / "performance.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8"
    )
    performance_handler.setLevel(logging.DEBUG)
    # Filtro para capturar solo logs de timing
    performance_handler.addFilter(lambda record: "[TIMING]" in record.getMessage())
    performance_handler.setFormatter(formatter)
    root_logger.addHandler(performance_handler)
    
    # 4. Handler para requests HTTP
    requests_handler = RotatingFileHandler(
        filename=LOGS_DIR / "requests.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8"
    )
    requests_handler.setLevel(logging.INFO)
    # Filtro para capturar solo logs de requests
    requests_handler.addFilter(lambda record: "[REQUEST]" in record.getMessage())
    requests_handler.setFormatter(formatter)
    root_logger.addHandler(requests_handler)
    
    # ============== LOGGERS ESPECÍFICOS ==============
    
    # Reducir verbosidad de librerías externas
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    
    # Logger inicial
    logger = logging.getLogger(__name__)
    logger.info("=" * 80)
    logger.info(f"Sistema de logging inicializado - Nivel: {logging.getLevelName(level)}")
    logger.info(f"Directorio de logs: {LOGS_DIR.absolute()}")
    logger.info(f"Tamaño máximo por archivo: {MAX_BYTES / (1024*1024):.0f} MB")
    logger.info(f"Archivos de backup: {BACKUP_COUNT}")
    logger.info("=" * 80)


class TimingLogger:
    """
    Context manager para medir y loggear tiempos de ejecución
    
    Uso:
        with TimingLogger("Operación X"):
            # código a medir
            pass
    """
    
    def __init__(self, operation_name: str, logger_name: str = None, level: int = logging.INFO):
        self.operation_name = operation_name
        self.logger = logging.getLogger(logger_name or __name__)
        self.level = level
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.log(self.level, f"[TIMING] Iniciando: {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.log(
                self.level,
                f"[TIMING] Completado: {self.operation_name} | "
                f"Tiempo: {elapsed:.3f}s"
            )
        else:
            self.logger.error(
                f"[TIMING] Error en: {self.operation_name} | "
                f"Tiempo antes del error: {elapsed:.3f}s | "
                f"Error: {exc_val}"
            )
        
        return False  # No suprimir la excepción


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger configurado
    
    Args:
        name: Nombre del logger (usualmente __name__)
    
    Returns:
        Logger configurado
    """
    return logging.getLogger(name)