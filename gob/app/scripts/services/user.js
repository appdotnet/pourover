'use strict';

angular.module('pourOver').factory('LocalUser', ['$rootScope', 'LocalApiClient', 'Auth', function ($rootScope, ApiClient, Auth) {

  $rootScope.current_user = {};

  var getUser = function () {
    ApiClient.get({
      url: '/me'
    }).success(function (resp) {
      $rootScope.current_user = resp.data;
    });
  };

  if (Auth.isLoggedIn()) {
    getUser();
  } else {
    $rootScope.$on('login', getUser);
  }



  return {};
}]);