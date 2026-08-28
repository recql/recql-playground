-- Runs once on first boot (gvenzl /container-entrypoint-initdb.d).
-- APP_USER already creates `recql`; grant 23ai/26ai developer privileges (vector, etc.).

BEGIN
  EXECUTE IMMEDIATE 'GRANT DB_DEVELOPER_ROLE TO recql';
EXCEPTION
  WHEN OTHERS THEN NULL;
END;
/
