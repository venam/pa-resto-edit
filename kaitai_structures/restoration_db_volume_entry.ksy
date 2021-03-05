meta:
  id: restoration_db_volume_entry
  file-extension: .tdb
  endian: be
seq:
  - id: version
    type: pa_u8
  - id: volume_valid
    type: u1
    enum: pa_bool
  - id: channel_map
    type: pa_channel_map
  - id: volume
    type: pa_volume
  - id: muted_valid
    type: u1
    enum: pa_bool
  - id: muted
    type: u1
    enum: pa_bool
  - id: number_of_formats
    type: pa_u8
  - id: formats
    type: pa_formats
    repeat: expr
    repeat-expr: number_of_formats.value
types:
  pa_u8:
    seq:
      - id: type
        contents: 'B'
      - id: value
        type: u1
  pa_channel_map:
    seq:
      - id: type
        contents: 'm'
      - id: channels
        type: u1
      - id: values
        type: u1
        repeat: expr
        repeat-expr: channels
  pa_volume:
    seq:
      - id: type
        contents: 'v'
      - id: channels
        type: u1
      - id: values
        type: s4
        repeat: expr
        repeat-expr: channels
  pa_formats:
    seq:
      - id: type
        contents: 'f'
      - id: encoding
        type: pa_u8
      - id: plist
        type: pa_plist
  pa_plist:
    seq:
      - id: type
        contents: 'P'
      - id: string_type
        type: u1
      - id: plist
        type: strz
        encoding: ASCII
        if: string_type == 0x74
enums:
  pa_bool:
   '1': true
   '0': false

