'use strict';
window.AUTH_DATA = window.AUTH_DATA || {};
console.log("Outside adn auth", window.AUTH_DATA);
angular.module('adn').factory('Auth', function ($rootScope, $location) {
  console.log("Inside Adn auth AUTH_DATA:", window.AUTH_DATA);
  $rootScope.local = window.AUTH_DATA;
  $rootScope.$watch('local', function () {
    window.AUTH_DATA = $rootScope.local;
  }, true);
  console.log("Inside Adn auth AUTH_DATA", window.AUTH_DATA, 'local', $rootScope.local);
  return {
    isLoggedIn: function (local) {
      if(local === undefined) {
        local = $rootScope.local;
      }
      return local && typeof(local.accessToken) !== 'undefined';
    },
    logout: function () {
      $rootScope.local = {};
      window.AUTH_DATA = {};
      $rootScope.$broadcast('logout');
    },
    login: function () {
      $rootScope.local.accessToken = jQuery.url($location.absUrl()).fparam('access_token') || $rootScope.local.accessToken;
      $location.hash('');
      $rootScope.$broadcast('login');
    }
  };

});