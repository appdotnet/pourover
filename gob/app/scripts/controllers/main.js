'use strict';

(function () {
  var MainCtrl = function ($rootScope, $scope, ApiClient, $routeParams, $location, Feeds, User) {
    Feeds.setNewFeed();
    $scope.valid_feed = false;

    var throttled_updates = _.throttle(function () {
      Feeds.validateFeed($scope.feed).then(function (feed) {
        $scope.valid_feed = true;
        feed.feed_url = $rootScope.feed.feed_url;
        $rootScope.feed = feed;
      }).always(function () {
        jQuery('.loading-icon').hide();
      });
    }, 100);

    $scope.$watch('feed.feed_url', function () {
      $scope.valid_feed = false;
      if (!$scope.feed || !$scope.feed.feed_url) {
        return;
      }
      jQuery('.loading-icon').show();
      throttled_updates();
    });

    var updateLoader = Ladda.create(jQuery('[data-save-btn]').get(0));
    $scope.createFeed = function () {
      updateLoader.start();
      debugger;
      Feeds.createFeed($rootScope.feed).then(function (feed) {
        $("#newFeedModal").modal('hide');
        $location.path('/feed/' + feed.feed_id);
      }, function () {
        window.alert('Something wen\'t wrong while saving your feed');
      }).always(updateLoader.stop);

      return false;
    };


  };

  MainCtrl.$inject = ['$rootScope', '$scope', 'ApiClient', '$routeParams', '$location', 'Feeds', 'User'];
  angular.module('pourOver').controller('MainCtrl', MainCtrl);
})();
