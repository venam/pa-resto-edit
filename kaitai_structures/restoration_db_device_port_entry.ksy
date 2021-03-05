meta:
  id: restoration_db_device_port_entry
  file-extension: .tdb
  endian: be
seq:
  - id: version
    type: pa_u8
  - id: port_valid
    type: u1
    enum: pa_bool
  - id: port
    type: pa_port
types:
  pa_u8:
    seq:
      - id: type
        contents: 'B'
      - id: value
        type: u1
  pa_port:
    seq:
      - id: string_type
        type: u1
      - id: name
        type: strz
        encoding: ASCII
        if: string_type == 0x74
enums:
  pa_bool:
   '1': true
   '0': false

