'use strict';

angular.module('pourOver').factory('User', ['$rootScope', 'ApiClient', function ($rootScope, ApiClient) {

  $rootScope.current_user = {};

  ApiClient.get({
    url: 'me'
  }).success(function (resp, status, headers, config) {
    $rootScope.current_user = resp.data;
  });

  return {};
}]);