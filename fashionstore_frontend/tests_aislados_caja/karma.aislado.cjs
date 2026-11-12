// Chrome temporal: únicamente loopback para Karma; sin salida a proveedores.
module.exports = function(config) {
  require('../karma.conf.js')(config);
  config.set({reporters:['progress'], customLaunchers:{ChromeCajaAislada:{
    base:'ChromeHeadless', flags:['--no-sandbox','--disable-gpu','--disable-background-networking',
      '--disable-component-update','--disable-sync','--proxy-server=http://127.0.0.1:9',
      '--proxy-bypass-list=127.0.0.1;localhost']
  }}, browsers:['ChromeCajaAislada']});
};
