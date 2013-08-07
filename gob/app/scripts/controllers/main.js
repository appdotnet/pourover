'use strict';

(function () {
  var MainCtrl = function ($rootScope, $scope, ApiClient, $routeParams, $location, Feeds, User) {
    Feeds.setNewFeed();
  };

  MainCtrl.$inject = ['$rootScope', '$scope', 'ApiClient', '$routeParams', '$location', 'Feeds', 'User'];
  angular.module('pourOver').controller('MainCtrl', MainCtrl);
})();
