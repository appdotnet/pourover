'use strict';

angular.module('pourOver').factory('Auth', ['$rootScope', '$location', function ($rootScope, $location) {
  $rootScope.local = JSON.parse((typeof(localStorage.data) !== 'undefined') ? localStorage.data : '{}');
  $rootScope.$watch('local', function () {
    localStorage.data = JSON.stringify($rootScope.local);
  }, true);

  return {
    isLoggedIn: function (local) {
      if(local === undefined) {
        local = $rootScope.local;
      }
      return local && typeof(local.accessToken) !== 'undefined';
    },
    logout: function () {
      $rootScope.local = {};
      localStorage.clear();
    },
    login: function () {
      $location.hash('');
      $rootScope.local.accessToken = $rootScope.local.accessToken || jQuery.url(window.location).fparam('access_token');
    }
  };

}]);