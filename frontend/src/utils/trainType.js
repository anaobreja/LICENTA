const MAP = {
  intercity: 'IC',
  interregio: 'IR',
  regio: 'R',
}

export function fmtTrainType(type) {
  if (!type) return ''
  return MAP[type.toLowerCase()] ?? type.toUpperCase()
}
