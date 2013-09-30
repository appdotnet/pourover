'use strict';

(function () {
  var MainCtrl = function ($rootScope, $scope, ApiClient, $routeParams, $location, Feeds, debounce) {
    Feeds.setNewFeed();
    $scope.valid_feed = false;
    $scope.feed_error = false;
    var throttled_updates = debounce(function () {
      Feeds.validateFeed($scope.feed).then(function (feed) {
        $scope.valid_feed = !!feed.feed_url;
        //feed.feed_url = $rootScope.feed.feed_url;
        $rootScope.feed = feed;
      }, function (error) {
        $scope.feed_error = error;
      }).always(function () {
        jQuery('.loading-icon').hide();
      });
    }, 200);

    $scope.$watch('feed.feed_url', function () {
      $scope.valid_feed = false;
      $scope.feed_error = false;
      if (!$scope.feed || !$scope.feed.feed_url) {
        return;
      }

      jQuery('.loading-icon').show();
      throttled_updates();
    });

    $scope.createFeed = function () {
      var button = jQuery('[data-save-btn]');
      button.attr("disabled", "disabled");
      button.html('<i class="icon-refresh icon-spin"></i>');
      Feeds.createFeed($rootScope.feed).then(function (feed) {
        jQuery('#newFeedModal').modal('hide');
        $location.path('/feed/' + feed.feed_type + '/' + feed.feed_id + '/').hash('settings');
      }, function () {
        window.alert('Something wen\'t wrong while saving your feed');
      }).always(function () {
        button.attr("disabled", null);
        button.html('Add Feed');
      });

      return false;
    };


  };

  MainCtrl.$inject = ['$rootScope', '$scope', 'LocalApiClient', '$routeParams', '$location', 'Feeds', 'debounce'];
  angular.module('pourOver').controller('MainCtrl', MainCtrl);
})();
