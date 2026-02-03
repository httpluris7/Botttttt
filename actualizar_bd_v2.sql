-- ============================================================
-- ACTUALIZACIÓN BASE DE DATOS v2.0
-- Nuevas funcionalidades: rutas frecuentes, estadísticas
-- ============================================================

-- TABLA: Rutas frecuentes (aprende de los viajes realizados)
CREATE TABLE IF NOT EXISTS rutas_frecuentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origen TEXT NOT NULL,
    destino TEXT NOT NULL,
    km_estimados INTEGER DEFAULT 0,
    tiempo_estimado TEXT DEFAULT '',
    veces_realizada INTEGER DEFAULT 1,
    ultimo_viaje DATE,
    km_total_acumulado INTEGER DEFAULT 0,
    consumo_promedio REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(origen, destino)
);

-- TABLA: Gastos de viajes
CREATE TABLE IF NOT EXISTS gastos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    viaje_id INTEGER,
    conductor TEXT,
    categoria TEXT NOT NULL,  -- COMBUSTIBLE, PEAJE, DIETA, PARKING, OTROS
    importe REAL NOT NULL,
    descripcion TEXT,
    fecha DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (viaje_id) REFERENCES viajes(id)
);

-- TABLA: Historial de backups
CREATE TABLE IF NOT EXISTS backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archivo TEXT,
    tamaño_kb INTEGER,
    destino TEXT,  -- LOCAL, DRIVE, EMAIL
    estado TEXT DEFAULT 'OK'
);

-- TABLA: Logs de errores críticos
CREATE TABLE IF NOT EXISTS logs_criticos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modulo TEXT,
    nivel TEXT,  -- ERROR, CRITICAL
    mensaje TEXT,
    notificado INTEGER DEFAULT 0
);

-- TABLA: Informes generados
CREATE TABLE IF NOT EXISTS informes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT,  -- SEMANAL, MENSUAL, CONDUCTOR
    fecha_inicio DATE,
    fecha_fin DATE,
    datos_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ÍNDICES para mejor rendimiento
CREATE INDEX IF NOT EXISTS idx_rutas_origen ON rutas_frecuentes(origen);
CREATE INDEX IF NOT EXISTS idx_rutas_destino ON rutas_frecuentes(destino);
CREATE INDEX IF NOT EXISTS idx_gastos_viaje ON gastos(viaje_id);
CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);
CREATE INDEX IF NOT EXISTS idx_logs_fecha ON logs_criticos(fecha);

-- VISTA: Resumen de rutas más frecuentes
CREATE VIEW IF NOT EXISTS v_rutas_top AS
SELECT 
    origen,
    destino,
    km_estimados,
    tiempo_estimado,
    veces_realizada,
    ultimo_viaje,
    ROUND(km_total_acumulado * 1.0 / NULLIF(veces_realizada, 0), 0) as km_promedio
FROM rutas_frecuentes
ORDER BY veces_realizada DESC
LIMIT 20;

-- VISTA: Gastos por categoría
CREATE VIEW IF NOT EXISTS v_gastos_categoria AS
SELECT 
    categoria,
    COUNT(*) as num_gastos,
    SUM(importe) as total,
    ROUND(AVG(importe), 2) as promedio
FROM gastos
WHERE fecha >= date('now', '-30 days')
GROUP BY categoria
ORDER BY total DESC;

-- TRIGGER: Actualizar fecha de modificación en rutas
CREATE TRIGGER IF NOT EXISTS trg_rutas_updated
AFTER UPDATE ON rutas_frecuentes
BEGIN
    UPDATE rutas_frecuentes SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================
-- DATOS INICIALES DE RUTAS CONOCIDAS
-- ============================================================

INSERT OR IGNORE INTO rutas_frecuentes (origen, destino, km_estimados, tiempo_estimado, veces_realizada) VALUES
('AZAGRA', 'MADRID', 320, '3h 30min', 0),
('AZAGRA', 'BARCELONA', 350, '3h 45min', 0),
('AZAGRA', 'ZARAGOZA', 120, '1h 20min', 0),
('AZAGRA', 'BILBAO', 180, '2h 00min', 0),
('AZAGRA', 'VALENCIA', 380, '4h 00min', 0),
('MELIDA', 'MADRID', 330, '3h 40min', 0),
('MELIDA', 'BARCELONA', 340, '3h 40min', 0),
('MELIDA', 'BADAJOZ', 580, '6h 00min', 0),
('MELIDA', 'SEVILLA', 680, '7h 00min', 0),
('TUDELA', 'MADRID', 310, '3h 20min', 0),
('TUDELA', 'ZARAGOZA', 90, '1h 00min', 0),
('PAMPLONA', 'MADRID', 400, '4h 15min', 0),
('PAMPLONA', 'BARCELONA', 420, '4h 30min', 0),
('PERALTA', 'MERCAMADRID', 330, '3h 35min', 0),
('CALAHORRA', 'MADRID', 290, '3h 10min', 0),
('LOGROÑO', 'MADRID', 330, '3h 30min', 0),
('LOGROÑO', 'BARCELONA', 420, '4h 30min', 0);

COMMIT;
