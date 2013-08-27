'use strict';

angular.module('pourOver').factory('LocalUser', ['$rootScope', 'LocalApiClient', function ($rootScope, ApiClient) {

  $rootScope.current_user = {};

  ApiClient.get({
    url: '/me'
  }).success(function (resp) {
    $rootScope.current_user = resp.data;
  });

  return {};
}]);