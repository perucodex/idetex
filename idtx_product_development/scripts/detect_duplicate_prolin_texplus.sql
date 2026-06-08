-- Diagnostico (SOLO LECTURA) de fases repetidas en TEXPLUS PROLIN.
-- Ejecutar en el SQL Server de TEXPLUS. NO modifica nada.
--
-- PROLIN = lineas de fase por proceso (ruta). La clave natural es
-- (EmprCod, ProCod, ProNumLin). Un mismo FasCod puede aparecer en varios
-- ProNumLin: a veces legitimo, a veces duplicado espurio (lo que se ve en
-- la captura: 5x CEPILLADO DE TELA seguidas).
--
-- Ajusta @Empr si tu empresa no es '001'.

DECLARE @Empr CHAR(3) = '001';

-- 1) Procesos donde un mismo FasCod aparece mas de una vez.
--    Util para localizar las rutas a revisar. Ordenado por mayor repeticion.
SELECT
    LTRIM(RTRIM(l.ProCod))            AS ProCod,
    LTRIM(RTRIM(l.FasCod))            AS FasCod,
    COALESCE(NULLIF(LTRIM(RTRIM(f.FasDsc)), ''), LTRIM(RTRIM(l.FasCod))) AS FaseDsc,
    COUNT(*)                          AS Veces,
    MIN(l.ProNumLin)                  AS PrimeraLinea,
    MAX(l.ProNumLin)                  AS UltimaLinea
FROM dbo.PROLIN l
LEFT JOIN dbo.FASPRO f
    ON f.EmprCod = l.EmprCod AND f.FasCod = l.FasCod
WHERE l.EmprCod = @Empr
GROUP BY LTRIM(RTRIM(l.ProCod)), LTRIM(RTRIM(l.FasCod)),
         COALESCE(NULLIF(LTRIM(RTRIM(f.FasDsc)), ''), LTRIM(RTRIM(l.FasCod)))
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC, ProCod, FasCod;

-- 2) Detalle linea por linea de un proceso concreto (cambia 'ESTPIGAC').
--    Permite ver si las repeticiones son CONSECUTIVAS (ProNumLin contiguos),
--    senal fuerte de duplicado espurio.
SELECT
    l.ProNumLin,
    LTRIM(RTRIM(l.FasCod))            AS FasCod,
    COALESCE(NULLIF(LTRIM(RTRIM(f.FasDsc)), ''), NULLIF(LTRIM(RTRIM(l.Dtp_FasDsc)), ''), LTRIM(RTRIM(l.FasCod))) AS FaseDsc
FROM dbo.PROLIN l
LEFT JOIN dbo.FASPRO f
    ON f.EmprCod = l.EmprCod AND f.FasCod = l.FasCod
WHERE l.EmprCod = @Empr
  AND LTRIM(RTRIM(l.ProCod)) = 'ESTPIGAC'
ORDER BY l.ProNumLin;

-- 3) (OPCIONAL) Una vez confirmados los duplicados espurios, ejemplo de
--    limpieza. REVISAR ANTES DE EJECUTAR y hacer respaldo. Borra las lineas
--    duplicadas dejando solo la de menor ProNumLin por (ProCod, FasCod).
--    >>> Descomenta solo si estas seguro y para los ProCod correctos. <<<
--
-- WITH dups AS (
--     SELECT l.*,
--            ROW_NUMBER() OVER (
--                PARTITION BY l.EmprCod, l.ProCod, l.FasCod
--                ORDER BY l.ProNumLin
--            ) AS rn
--     FROM dbo.PROLIN l
--     WHERE l.EmprCod = @Empr
--       AND LTRIM(RTRIM(l.ProCod)) = 'ESTPIGAC'
-- )
-- DELETE FROM dups WHERE rn > 1;
