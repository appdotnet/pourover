'use strict';

angular.module('pourOver').factory('LocalUser', ['$rootScope', 'LocalApiClient', 'Auth', 'ApiClient', '$location', function ($rootScope, ApiClient, Auth, UpstreamApiClient, $location) {

  $rootScope.current_user = {};

  var getUser = function () {
    ApiClient.get({
      url: '/me'
    }).success(function (resp) {
      $rootScope.current_user = resp.data;
      console.log(resp.data);
    });

    UpstreamApiClient.get({
      url: '/token'
    }).success(function (resp) {
      var has_permissions = _.all(["messages", "write_post", "basic"], function(v){
        return _.include(resp.data.scopes, v);
      });
      if (!has_permissions) {
        window.alert('Please logout, and login again');
        $location.path('/logout');
      }
    });

  };

  if (Auth.isLoggedIn()) {
    getUser();
  } else {
    $rootScope.$on('login', getUser);
  }



  return {};
}]);