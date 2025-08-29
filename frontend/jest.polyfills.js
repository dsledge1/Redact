// Polyfill for TextEncoder/TextDecoder
const { TextEncoder, TextDecoder } = require('util');
global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Polyfill for fetch API
require('whatwg-fetch');

// Polyfill for structured cloning
global.structuredClone = (val) => JSON.parse(JSON.stringify(val));