const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8085;
const APP_PATH = path.join(__dirname, 'index.html');

const server = http.createServer((req, res) => {
  fs.readFile(APP_PATH, 'utf8', (err, data) => {
    if (err) {
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end('Error loading prototype HTML: ' + err.message);
    } else {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(data);
    }
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Mighty Mouse Prototype server running at http://localhost:${PORT}`);
});
