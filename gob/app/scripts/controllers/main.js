'use strict';

(function () {
  var MainCtrl = function ($rootScope, $scope, ApiClient, $routeParams, $location, Feeds, User) {
    Feeds.setNewFeed();
    $scope.valid_feed = false;

    $scope.$watch('feed.feed_url', _.debounce(Feeds.validateFeed));
  };

  MainCtrl.$inject = ['$rootScope', '$scope', 'ApiClient', '$routeParams', '$location', 'Feeds', 'User'];
  angular.module('pourOver').controller('MainCtrl', MainCtrl);
})();
