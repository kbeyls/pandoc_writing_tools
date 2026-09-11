# Sanitized Confluence Server draw.io contract

These fixtures preserve only the storage-format details needed to test the
uploader. They were derived from a read-only inspection of one diagram on the
target Confluence Server/Data Center installation. Hostnames, page IDs, macro
IDs, diagram content, and user data were replaced.

The installed app uses macro name `drawio`. Its `diagramName` is the basename
of an extensionless diagram attachment with media type
`application/vnd.jgraph.mxfile`. A PNG attachment named `<diagramName>.png`
provides the preview. The macro's numeric `revision` matches the current
diagram-source attachment version. The observed viewer settings were
`links=auto`, `simpleViewer=false`, `tbstyle=top`, and `lbox=true`.

The diagram attachment contained uncompressed `<mxfile>` XML. The temporary
draft attachment created by the interactive editor is not required when
publishing an already complete diagram through the REST API.
